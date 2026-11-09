import argparse
import csv
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from heredity import (PROBS, load_data, powerset, gene_count,
                      joint_probability, update, normalize)


ORIGIN_PATH = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER_PATH = os.path.join(ORIGIN_PATH, "data")
STATIC_DIR = os.path.join(ORIGIN_PATH, "static")

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


DEFAULT_MUTATION = PROBS["mutation"]

# Inferência exata testa 2^n * 3^n combinações
MAX_PEOPLE = 8


# ---------------------------------------------------------------------------
# calculo como em hereidty
# ---------------------------------------------------------------------------

def compute(people, known_genes, mutation):
    """
    Calcula as probabilidades de cada pessoa, como o main() do heredity.py.

    people       - igual load_data com o "trait" de cada pessoa já trocado pelo que se escolheu na página
    known_genes  - {nome: 0, 1 ou 2} para quem tem n de genes conhecido
    mutation     - taxa de mutacao escolhida no slider
    """

    probabilities = {
        person: {"gene": {2: 0, 1: 0, 0: 0}, "trait": {True: 0, False: 0}}
        for person in people
    }
    names = set(people)

    # Troca a mutação só durante este cálculo
    original_mutation = PROBS["mutation"]
    PROBS["mutation"] = mutation
    try:
        #todos os conjuntos possíveis de quem tem o traço
        for have_trait in powerset(names):

            # salta se contradiz o que se sabe sobre o trait
            fails_evidence = any(
                people[person]["trait"] is not None
                and people[person]["trait"] != (person in have_trait)
                for person in names
            )
            if fails_evidence:
                continue

            # todas as distribuições de 1 e 2 genes
            for one_gene in powerset(names):
                for two_genes in powerset(names - one_gene):

                    # salta se contradiz um n de genes conhecido
                    if any(gene_count(person, one_gene, two_genes) != genes
                           for person, genes in known_genes.items()):
                        continue

                    # soma a probabilidade desta combinação
                    p = joint_probability(people, one_gene, two_genes, have_trait)
                    update(probabilities, one_gene, two_genes, have_trait, p)
    finally:
        PROBS["mutation"] = original_mutation

    # Se tudo deu 0, o normalize, avisa caso 0
    total = sum(probabilities[next(iter(people))]["trait"].values())
    if total == 0:
        raise ValueError("This combination is impossible under the model "
                         "(every possibility has probability 0). "
                         "Try a mutation rate above 0.")

    # cada distribuição passa a somar 1
    normalize(probabilities)
    return probabilities


# ---------------------------------------------------------------------------
# Famílias e posição de cada pessoa na árvore
# ---------------------------------------------------------------------------

def list_families():
    """Ficheiros CSV em data/ com as colunas que o heredity.py espera."""
    families = []
    for filename in sorted(os.listdir(DATA_FOLDER_PATH)):
        if not filename.endswith(".csv"):
            continue
        # Lê só a primeira linha (nomes das colunas) para ver as colunas
        with open(os.path.join(DATA_FOLDER_PATH, filename)) as f:
            header = next(csv.reader(f), [])
        if {"name", "mother", "father", "trait"} <= set(header):
            families.append(filename)
    return families


def family_path(filename):
    """Caminho do CSV so aceita ficheiros da lista."""
    if filename not in list_families():
        raise ValueError(f"unknown family file: {filename}")
    return os.path.join(DATA_FOLDER_PATH, filename)


def generations(people):
    """
    Linha geraçao de cada pessoa na arvore:
    filhos ficam uma linha abaixo dos pais, casais na mesma linha.
    """
    # casais = duas pessoas que têm um filho em comum
    couples = {name: set() for name in people}
    for person in people.values():
        if person["mother"]:
            couples[person["mother"]].add(person["father"])
            couples[person["father"]].add(person["mother"])

    # Repete até nada mudar
    gen = {name: 0 for name in people}
    changed = True
    while changed:
        changed = False
        for name, person in people.items():
            if person["mother"]:
                # Filho: uma linha abaixo do pai/mãe mais abaixo
                g = max(gen[person["mother"]], gen[person["father"]]) + 1
                if gen[name] < g:
                    gen[name], changed = g, True
            else:
                # Sem pais nos dados: fica na linha dos casais
                for spouse in couples[name]:
                    if gen[spouse] > gen[name]:
                        gen[name], changed = gen[spouse], True
    return gen, couples


def layout(people):
    """Devolve {nome: [coluna, linha]}; a página converte"""
    gen, couples = generations(people)

    # Agrupa as pessoas por linha
    rows = {}
    for name in people:
        rows.setdefault(gen[name], []).append(name)

    column = {}
    for g in sorted(rows):
        # filhos ordenados pela posicao medias dos pais
        with_parents = sorted(
            (n for n in rows[g] if people[n]["mother"]),
            key=lambda n: (column[people[n]["mother"]] + column[people[n]["father"]]) / 2)
        founders = sorted(n for n in rows[g] if not people[n]["mother"])

        # cada pessoa seguida logo do seu parceiro
        ordered, placed = [], set()
        for name in with_parents + founders:
            if name in placed:
                continue
            ordered.append(name)
            placed.add(name)
            for spouse in sorted(couples[name]):
                if spouse not in placed and gen[spouse] == g:
                    ordered.append(spouse)
                    placed.add(spouse)

        # Colunas centradas em 0
        for i, name in enumerate(ordered):
            column[name] = i - (len(ordered) - 1) / 2

    return {name: [column[name], gen[name]] for name in people}


def family_info(filename):
    """Dados de uma familia para a pagina desenhar a arvore."""
    people = load_data(family_path(filename))
    positions = layout(people)
    return {
        "file": filename,
        "people": [
            {
                "name": name,
                "mother": person["mother"],
                "father": person["father"],
                "trait": person["trait"],
                "pos": positions[name],
            }
            for name, person in people.items()
        ],
        "mutation": DEFAULT_MUTATION,
        "tooBig": len(people) > MAX_PEOPLE,
    }


def run_inference(request):
    """
    Recebe o que esta escolhido na pagina e devolve as probabilidades.

    request = {
        "file": "family0.csv",
        "evidence": {"Harry": {"trait": true / false / null,
                               "gene": 0 / 1 / 2 / null}, ...},
        "mutation": 0.01
    }
    """
    # carrega o CSV com o load_data
    people = load_data(family_path(request["file"]))
    if len(people) > MAX_PEOPLE:
        raise ValueError(f"{len(people)} people is too many for live exact "
                         f"inference (max {MAX_PEOPLE}).")

    # substitui os dados do CSV pelo que se escolheu na pagina
    known_genes = {}
    for name, evidence in request.get("evidence", {}).items():
        if name not in people:
            raise ValueError(f"unknown person: {name}")
        if evidence.get("trait") not in (True, False, None):
            raise ValueError(f"bad trait value for {name}")
        people[name]["trait"] = evidence.get("trait")
        if evidence.get("gene") is not None:
            if evidence["gene"] not in (0, 1, 2):
                raise ValueError(f"bad gene value for {name}")
            known_genes[name] = evidence["gene"]

    mutation = float(request.get("mutation", DEFAULT_MUTATION))
    if not 0 <= mutation <= 0.5:
        raise ValueError("mutation must be between 0 and 0.5")

    # calcula e mede quanto tempo demorou, 
    start = time.perf_counter()
    probabilities = compute(people, known_genes, mutation)
    elapsed = time.perf_counter() - start

    # JSON nao aceita numeros como chaves: genes 0/1/2 passam a texto
    return {
        "ms": round(elapsed * 1000, 1),
        "results": {
            name: {
                "gene": {str(g): p for g, p in probs["gene"].items()},
                "trait": probs["trait"][True],
            }
            for name, probs in probabilities.items()
        },
    }


# ---------------------------------------------------------------------------
# servidor web
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        """Envia uma resposta em JSON."""
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, filename):
        """Envia um ficheiro de static."""
        if filename not in os.listdir(STATIC_DIR):
            self.send_json({"error": "not found"}, 404)
            return
        extension = os.path.splitext(filename)[1]
        with open(os.path.join(STATIC_DIR, filename), "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(extension, "text/plain"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # carrega sempre a versão mais recente
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Pedidos GET: a pagina e os dados das familias."""
        try:
            if self.path == "/":
                self.send_static("index.html")
            elif self.path.startswith("/static/"):
                self.send_static(self.path[len("/static/"):])
            elif self.path == "/api/families":
                self.send_json(list_families())
            elif self.path.startswith("/api/family/"):
                self.send_json(family_info(self.path[len("/api/family/"):]))
            else:
                self.send_json({"error": "not found"}, 404)
        except ValueError as e:
            self.send_json({"error": str(e)}, 400)

    def do_POST(self):
        """Pedido POST: calcular as probabilidades (/api/infer)."""
        if self.path != "/api/infer":
            self.send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length))
            self.send_json(run_inference(request))
        except (ValueError, KeyError, TypeError) as e:
            self.send_json({"error": str(e)}, 400)

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Live heredity explorer")
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()

    if not os.path.isdir(DATA_FOLDER_PATH):
        raise SystemExit("data/ not found next to app.py")
    if not os.path.isfile(os.path.join(STATIC_DIR, "index.html")):
        raise SystemExit("static/index.html not found next to app.py")


    server = HTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"Heredity explorer running at {url}")
    print(f"Open it in your browser, or run:  explorer.exe {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()