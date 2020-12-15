from lxml import etree
import requests
import click
import csv
import sys


def search_query(keyword, gallica=False):
    """Effectue une requête http sur l'API de recherche SRU Gallica.
    Selon le terme de recherche, affiche le nombre de résultat.
    Effectue une nouvelle requête http sur l'API SRU Gallica selon le choix de pagination.
    Création d'une liste d'identifiants arks.

    :param keyword: terme de recherche. Peut correspondre à plusieurs mots.
    :type keyword: str
    :return: liste des identifiants ark de la recherche.
    :rtype: list
    """

    # Transformation des espaces en %20 afin de pouvoir composer une requête de recherche à plusieurs mots.
    for char in keyword:
        keyword = keyword.replace(" ", "%20")

    # Requête http
    if gallica:
        url_query = "https://gallica.bnf.fr/SRU?operation=searchRetrieve&version=1.2&maximumRecords=10&startRecord=1&query=dc.type%20any%20image%20and%20gallica%20all%20{0}".format(keyword)
    else:
        url_query = "https://gallica.bnf.fr/SRU?operation=searchRetrieve&version=1.2&maximumRecords=10&startRecord=1&query=dc.type%20any%20image%20and%20metadata%20all%20{0}".format(keyword)
    print("Fetching: {0}".format(url_query))
    r = requests.get(url_query)

    # On transforme la requête en arbre XML exploitable
    xml_object = etree.fromstring(r.content)

    # On cherche la balise <srw:numberOfRecords> à l'aide d'une requête xpath. Prend en argument le nom de la balise et le namespace associé.
    node_records = xml_object.xpath("//srw:numberOfRecords", namespaces={"srw": "http://www.loc.gov/zing/srw/"})

    # Transformation du noeud récupéré en str.
    for node_record in node_records:
        node_record = node_record.text

    # pagination de la recherche
    if int(node_record) > 0 and int(node_record) <= 10:
        print(node_record)
        start_record = 1
    elif int(node_record) > 10:
        print("Il y a {0} records. A partir de quel record souhaitez-vous paginer la recherche ?".format(str(node_record)))
        start_record = int(input("-> "))
    else:
        print("Aucun résultat")
        sys.exit()

    # Nouvelle requête http permettant de paginer selon le choix de l'utilisateur.rice avec start_record.
    if gallica:
        url_query = "https://gallica.bnf.fr/SRU?operation=searchRetrieve&version=1.2&maximumRecords=10&startRecord={0}&query=dc.type%20any%20image%20and%20gallica%20all%20{1}".format(str(start_record), keyword)
    else:
        url_query = "https://gallica.bnf.fr/SRU?operation=searchRetrieve&version=1.2&maximumRecords=10&startRecord={0}&query=dc.type%20any%20image%20and%20metadata%20all%20{1}".format(str(start_record), keyword)
    print("Fetching: {0}".format(url_query))
    r = requests.get(url_query)

    xml_object = etree.fromstring(r.content)
    # Récupération des balises <dc:identifier>, puis de la chaine de caractères correspondant à l'id ark.
    node = xml_object.xpath("//dc:identifier", namespaces={"dc": "http://purl.org/dc/elements/1.1/"})
    ark_list = []
    for ark in node:
        ark = ark.text
        if ark.startswith("http"):
            ark = ark[23:]
            if ark.startswith("ark"):
                test_request_ark = requests.get("https://gallica.bnf.fr/iiif/" + ark + "/manifest.json")
                if test_request_ark.status_code == 200:
                    ark_list.append(ark)
                else:
                    print("Request error ({0}) : {1}".format(ark, str(test_request_ark)))
    if not ark_list:
        print("Aucun identifiant ark pour la pagination choisie.")

    return ark_list

def ark_query(ark_list):
    """Effectue une requête http sur l'API IIIF Gallica à partir d'une liste d'identifiants ark.
    Pour chaque identifiant ark, extrait les métadonnées @id, title, creator et date.
    Génère un lien permettant la visualisation du manifest avec universalviewer.io.
    Stockage des données dans une liste.

    :param ark_list: liste contenant plusieurs identifiants ark
    :type ark_list: list
    :return: liste de listes qui contiennent chacune les métadonnées des id ark.
    :rtype: list
    """

    title = ""
    creator = ""
    date = ""
    metadata = []

    for ark in ark_list:
        # Pour chaque id ark, requête http sur l'API IIIF Gallica.
        url_query = "https://gallica.bnf.fr/iiif/" + ark + "/manifest.json"
        print("Fetching: {0}".format(url_query))
        r = requests.get(url_query)
        data = r.json()
        id = data['@id']

        """ Les métadonnées récupérées ne sont pas forcément présentes pour chaque id ark.
        la fonction any() permet de vérifier s'il existe une entrée {"label": "Title"}, grâce à une boucle
         dans la liste "metadata" de dictionnaires. Si la métadonnée existe, *
        attribution de {"value": "value_title"} à une variable.
         Si la métadonnée n'est pas renseignée, on attribue 'no data' à la variable."""
        if any(dict['label'] == 'Title' for dict in data['metadata']):
            for dict in data['metadata']:
                if dict['label'] == 'Title':
                    title = dict['value']
        else:
            creator = "no data"

        if any(dict['label'] == 'Creator' for dict in data['metadata']):
            for dict in data['metadata']:
                if dict['label'] == 'Creator':
                    if type(dict['value']) == str:
                        creator = dict['value']
                    elif type(dict['value']) == list:
                        for sub_dict in dict['value']:
                            creator += sub_dict["@value"] + " ; "
        else:
            creator = "no data"

        if any(dict['label'] == 'Date' for dict in data['metadata']):
            for dict in data['metadata']:
                if dict['label'] == 'Date':
                    if type(dict['value']) == str:
                        date = dict['value']
                    elif type(dict['value']) == list:
                        for sub_dict in dict['value']:
                            date += sub_dict["@value"] + " ; "
        else:
            date = "no data"

        universal_viewer_url = "http://universalviewer.io/uv.html?manifest=" + url_query

        metadata.append([id, title, creator, date, universal_viewer_url])

    return metadata


@click.group()
def group():
    """Requete http via l'API de recherche SRU Gallica. Recherche à partir des métadonnées par défaut.
    Propose une pagination des résultats de recherche et récupère 10 identifiants ark.
    Présente les métadonnées des identifiants arks récupérées,
    avec possibilité de les récupérer dans un fichier csv.
    """


@group.command("search")
@click.argument("keyword", type=str)
@click.option("-g", "--gallica", is_flag=True, default=False, help="Broader search")
@click.option("-o", "--output", "output_file", type=click.File(mode="w"), default=None,
              help="If csv file output is wanted, input file's name. --output_file [FILE_NAME]")
def run(keyword, gallica, output_file):
    """ Effectue une recherche en deux temps via les API Gallica. search [KEYWORD(S)]

    :param keyword: terme de recherche. Peut contenir plusieurs termes.
    :type keyword: str
    :param output_file: nom du fichier de sortie csv
    :type output_file: str
    """

    ark_list = search_query(keyword, gallica=gallica)
    metadata = ark_query(ark_list)

    a = 1
    for collected_data in metadata:
        print("Ark number {0} :".format(str(a)))
        print(collected_data)
        print("\n")
        a += 1

    if output_file:
        f = csv.writer(output_file)
        f.writerow(["ID", "Title", "Creator", "Date", "universalviewer.io"])
        for collected_data in metadata:
            f.writerow((collected_data))
        print("CSV file : done")


if __name__ == "__main__":
    group()
