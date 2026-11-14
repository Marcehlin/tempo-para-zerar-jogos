"""Monta dados/jogos_mlg.csv a partir dos dados coletados por coletar_dados.py.

Uso (na pasta do repositorio, depois de "python coletar_dados.py"):

    python montar_base.py

Etapas (as regras estao descritas no README):
  1. chave de juncao a partir do nome do jogo (minusculas, sem acentos e sem pontuacao);
  2. filtro dos registros do HowLongToBeat (tipo "game", ano conhecido, pelo menos
     MIN_RELATOS relatos de tempo da historia principal);
  3. juncao por nome, validada pelo ano de lancamento (diferenca maxima TOL_ANO),
     garantindo correspondencia 1 para 1;
  4. construcao das variaveis e limpeza final.

So usa a biblioteca padrao do Python.
"""
import csv
import os
import re
import math

csv.field_size_limit(10 ** 9)

MIN_RELATOS, TOL_ANO = 5, 1

_T = str.maketrans("ÀÁÂÃÄÅàáâãäåÈÉÊËèéêëÌÍÎÏìíîïÒÓÔÕÖòóôõöÙÚÛÜùúûüÇçÑñŌōŪū",
                   "AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCcNnOoUu")


def normaliza(x):
    x = x.translate(_T).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", x).strip()


GRUPOS = {
    "RPG": ["Action RPG", "JRPG", "Western RPG", "MMORPG", "RPG", "Trainer RPG", "Roguelike"],
    "Acao-Aventura": ["Action Adventure", "Open-World Action", "Linear Action Adventure", "Action",
                      "Survival", "Metroidvania", "Sandbox"],
    "Aventura": ["Adventure", "Point-and-Click", "First-Person Adventure", "Third-Person Adventure",
                 "Visual Novel", "Text Adventure", "Hidden Object"],
    "Tiro": ["FPS", "Third Person Shooter", "Tactical FPS", "Tactical Third Person Shooter",
             "Top-Down Shoot-'Em-Up", "Vertical Shoot-'Em-Up", "Horizontal Shoot-'Em-Up",
             "Light Gun", "Rail Shooter"],
    "Plataforma": ["2D Platformer", "3D Platformer"],
    "Luta": ["3D Fighting", "2D Fighting", "3D Beat-'Em-Up", "2D Beat-'Em-Up", "Wrestling", "Combat Sport"],
    "Estrategia": ["Real-Time Strategy", "Turn-Based Tactics", "Turn-Based Strategy", "Strategy",
                   "Command RTS", "Real-Time Tactics", "4X Strategy", "Defense", "MOBA",
                   "Card Battle", "Artillery"],
    "Simulacao": ["Tycoon", "Management", "Virtual Life", "Virtual Career", "Virtual Pet", "Simulation",
                  "Aircraft Combat Sim", "Vehicle Combat Sim", "Space Combat Sim", "Marine Combat Sim",
                  "Aircraft Sim", "Space Sim", "Vehicle Sim", "Train Sim", "Marine Sim"],
    "Puzzle": ["Action Puzzle", "Puzzle", "Matching Puzzle", "Logic Puzzle", "Stacking Puzzle"],
    "Esporte-Corrida": ["Auto Racing Sim", "Auto Racing", "Arcade Racing", "Future Racing", "Racing",
                        "Racing Sim", "Basketball Sim", "Football Sim", "Baseball Sim", "Soccer Sim",
                        "Hockey Sim", "Golf Sim", "Soccer Management", "Tennis", "Skating", "Golf",
                        "Skiing", "Soccer", "Athletics", "Basketball", "Biking", "Sports", "Football",
                        "Fishing", "Individual Sports", "Billiards", "Baseball", "Future Sport",
                        "Surfing", "Rugby", "Volleyball", "Hockey", "Team Sports", "Bowling",
                        "Hunting", "Horse Racing", "Cricket"],
}
MAPA_GENERO = {g: grupo for grupo, lista in GRUPOS.items() for g in lista}

COLUNAS = ["id_metacritic", "id_hltb", "titulo", "tempo_medio_h", "n_relatos", "metascore",
           "userscore", "n_criticas", "n_avaliacoes_usuarios", "ano", "genero",
           "genero_metacritic", "classificacao", "n_plataformas", "pc", "desenvolvedora",
           "regiao_empresa"]
TEXTO = {"titulo", "genero", "genero_metacritic", "classificacao", "desenvolvedora", "regiao_empresa"}


def arredonda2(x):
    """Arredonda para 2 casas: o candidato mais proximo de x em ponto flutuante (como o round do R)."""
    baixo, alto = math.floor(x * 100) / 100, math.ceil(x * 100) / 100
    d_baixo, d_alto = x - baixo, alto - x
    if d_baixo < d_alto:
        return baixo
    if d_alto < d_baixo:
        return alto
    return baixo if math.floor(x * 100) % 2 == 0 else alto


def num(x):
    return None if x in ("", None) else float(x)


def inteiro(x):
    v = num(x)
    return None if v is None else int(v)


def ano_de(data):
    try:
        return int((data or "")[:4])
    except ValueError:
        return None


def ler_estudios(caminho):
    tab = {}
    with open(caminho, encoding="utf-8", newline="") as f:
        for l in csv.DictReader(f):
            tab.setdefault(l["estudio"], []).append((int(l["a_partir_de"]), l["regiao_empresa"]))
    return tab


def montar(arq_notas, arq_tempos, arq_estudios):
    """Devolve (linhas, info). info traz as contagens intermediarias e os descartes."""
    info = {}
    notas = []
    with open(arq_notas, encoding="utf-8", newline="") as f:
        for l in csv.DictReader(f):
            l["chave"] = normaliza(re.sub(r"\s*\((19|20)[0-9]{2}\)\s*$", "", l["title"]))
            l["ano"] = ano_de(l["releaseDate"])
            l["id"] = int(l["id"])
            notas.append(l)
    info["metacritic"] = len(notas)

    hltb = {}
    n_tempos = 0
    with open(arq_tempos, encoding="utf-8", newline="") as f:
        for l in csv.DictReader(f):
            n_tempos += 1
            if l.get("game_game_type") != "game":
                continue
            ano = ano_de(l.get("game_release_world"))
            if ano is None or ano < 1970:
                continue
            chave = normaliza(l.get("game_game_name") or "")
            n, media = num(l.get("game_comp_main_count")), num(l.get("game_comp_main_avg"))
            if not chave or n is None or media is None or n < MIN_RELATOS or media <= 0:
                continue
            hltb.setdefault(chave, []).append(
                {"gid": int(float(l["game_game_id"])), "ano_hltb": ano, "n": int(n), "media": media})
    info["hltb_registros"] = n_tempos
    info["hltb_filtrados"] = sum(len(v) for v in hltb.values())

    pares = []
    for nt in notas:
        for h in hltb.get(nt["chave"], []) if nt["chave"] else []:
            pares.append((nt, h, None if nt["ano"] is None else abs(nt["ano"] - h["ano_hltb"])))
    info["pares_mesmo_nome"] = len(pares)
    info["mc_com_nome_no_hltb"] = len({p[0]["id"] for p in pares})
    pares = [p for p in pares if p[2] is not None and p[2] <= TOL_ANO]
    info["pares_ano_compativel"] = len(pares)
    info["mc_com_ano_compativel"] = len({p[0]["id"] for p in pares})

    pares.sort(key=lambda p: (p[0]["id"], p[2], -p[1]["n"], p[1]["gid"]))
    vistos, tmp = set(), []
    for p in pares:
        if p[0]["id"] not in vistos:
            vistos.add(p[0]["id"])
            tmp.append(p)

    def chave2(p):
        uc = num(p[0]["userscore_count"])
        return (p[1]["gid"], p[2], uc is None, -(uc or 0), p[0]["id"])

    tmp.sort(key=chave2)
    vistos, pares = set(), []
    for p in tmp:
        if p[1]["gid"] not in vistos:
            vistos.add(p[1]["gid"])
            pares.append(p)
    info["pareados"] = len(pares)

    estudios = ler_estudios(arq_estudios)

    linhas, desc = [], {"sem_nota_usuarios": 0, "sem_metascore_ou_plataforma": 0, "compilacao": 0,
                        "sem_genero": 0, "sem_desenvolvedora": 0}
    for nt, h, _ in pares:
        genres = nt["genres"]
        classif = nt["rating"]
        classif = {"K-A": "E", "AO": "M", "": "Sem classificacao", "RP": "Sem classificacao"}.get(classif, classif)
        plats = [p.strip() for p in nt["platforms"].split(",")] if nt["platforms"] else []
        dev = re.sub(r",.*$", "", nt["developer"], flags=re.S).strip()
        cand = [c for c in estudios.get(dev, []) if c[0] <= nt["ano"]]
        regiao = max(cand)[1] if cand else "desconhecido"
        tempo = arredonda2(h["media"] / 3600)
        linha = {
            "id_metacritic": nt["id"], "id_hltb": h["gid"], "titulo": nt["title"],
            "tempo_medio_h": tempo, "n_relatos": h["n"],
            "metascore": inteiro(nt["metascore"]), "userscore": inteiro(nt["userscore"]),
            "n_criticas": inteiro(nt["metascore_count"]),
            "n_avaliacoes_usuarios": inteiro(nt["userscore_count"]),
            "ano": nt["ano"], "genero": MAPA_GENERO.get(genres, "Outros"),
            "genero_metacritic": genres, "classificacao": classif,
            "n_plataformas": len(plats), "pc": int("PC" in plats),
            "desenvolvedora": dev, "regiao_empresa": regiao,
        }
        sem_u = nt["userscore_sentiment"] == ""
        sem_m = linha["metascore"] is None or linha["n_plataformas"] == 0
        desc["sem_nota_usuarios"] += sem_u
        desc["sem_metascore_ou_plataforma"] += sem_m
        desc["compilacao"] += genres == "Compilation"
        if sem_u or sem_m or genres == "Compilation":
            continue
        # jogos sem genero ou sem desenvolvedora no Metacritic tambem saem
        if genres == "":
            desc["sem_genero"] += 1
            continue
        if dev == "":
            desc["sem_desenvolvedora"] += 1
            continue
        linhas.append(linha)
    info["descartes"] = desc
    info["final"] = len(linhas)
    return linhas, info


def gravar(linhas, caminho, ordem=None):
    """Grava o CSV: textos entre aspas, numeros sem aspas, fim de linha LF."""
    def fmt(c, v):
        if c in TEXTO:
            return '"' + str(v).replace('"', '""') + '"'
        if isinstance(v, float):
            s = repr(v)
            return s[:-2] if s.endswith(".0") else s
        return str(v)
    if ordem:
        linhas = sorted(linhas, key=ordem)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(",".join('"%s"' % c for c in COLUNAS) + "\n")
        for l in linhas:
            f.write(",".join(fmt(c, l[c]) for c in COLUNAS) + "\n")


if __name__ == "__main__":
    pasta = os.path.dirname(os.path.abspath(__file__))
    linhas, info = montar(
        os.path.join(pasta, "Coleta", "games.csv"),
        os.path.join(pasta, "Coleta", "hltb_data.csv"),
        os.path.join(pasta, "dados", "estudios_regiao.csv"))
    saida = os.path.join(pasta, "dados", "tempo-para-zerar-jogos.csv")
    gravar(linhas, saida, ordem=lambda l: (l["titulo"].casefold(), l["ano"]))
    for chave, valor in info.items():
        print("%-24s %s" % (chave, valor))
    print("Arquivo gravado:", saida, "com", len(linhas), "linhas")
