"""Coleta dados atualizados do Metacritic e do HowLongToBeat.

Uso (em um terminal aberto na pasta do repositorio):

    python coletar_dados.py teste      # amostra de ~50 jogos (1 a 2 minutos)
    python coletar_dados.py            # coleta completa (pode ser interrompida e retomada)

So usa a biblioteca padrao do Python (nao precisa instalar nada).

Saidas (pasta Coleta/, que nao entra no repositorio):
    Coleta/games.csv        Metacritic, uma linha por jogo
    Coleta/hltb_data.csv    HowLongToBeat, uma linha por jogo (colunas game_*)
    Coleta/coleta.log       registro de erros e andamento
    Coleta/parcial/         arquivos de progresso (permitem retomar)
No modo teste os arquivos se chamam teste_games.csv, teste_hltb_data.csv e
teste_relatorio.txt. Depois da coleta, rode "python montar_base.py".

Como a coleta funciona:
  * Metacritic: a lista de jogos e percorrida em duas passagens (o site repete
    entradas entre paginas) e cada jogo e consultado pelo seu endereco. As
    resenhas individuais nao sao baixadas.
  * HowLongToBeat: sao visitados (a) os IDs de dados/hltb_ids.csv cujo nome
    coincide com o de algum jogo do Metacritic e (b) todos os IDs acima do
    maior ID desse arquivo. No fim, dados/hltb_ids.csv e atualizado com os IDs
    novos. Use "python coletar_dados.py --hltb-completo" para visitar todos os
    IDs conhecidos; sem dados/hltb_ids.csv a varredura comeca do ID 1.

Baseado na abordagem de dois projetos (o codigo aqui e novo):
  https://github.com/davutbayik/metacritic-backend-scraper (licenca MIT)
  https://github.com/zaireali649/howlongtobeat-scraper
"""

import csv
import gzip
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# --------------------------------------------------------------------------- configuracao
PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_IDS_HLTB = os.path.join(PASTA, "dados", "hltb_ids.csv")
ARQ_BASE_ATUAL = os.path.join(PASTA, "dados", "jogos_mlg.csv")
SAIDA = os.path.join(PASTA, "Coleta")
PARCIAL = os.path.join(SAIDA, "parcial")

MC_BASE = "https://backend.metacritic.com"
MC_CHAVE = "1MOZgmNFxvmljaQR1X9KAij9Mo4xAY3u"   # chave publica do site, a mesma do scraper original
HLTB_BASE = "https://howlongtobeat.com/game/"

AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

THREADS = 4            # requisicoes simultaneas por site
PAUSA = 0.25           # pausa (s) de cada thread depois de cada requisicao
TENTATIVAS = 4
MAX_404_SEGUIDOS = 1000   # criterio de parada da varredura de IDs novos (igual ao original)
MAX_BLOQUEIOS = 25        # falhas seguidas (403/429/erro) antes de desistir de um site

COLUNAS_MC = ["id", "title", "releaseDate", "rating", "genres", "description", "platforms",
              "metascore", "metascore_count", "metascore_sentiment", "userscore",
              "userscore_count", "userscore_sentiment", "platform_metascores",
              "developer", "publisher"]

csv.field_size_limit(10 ** 9)
_trava = threading.Lock()


class Bloqueado(Exception):
    pass


def log(msg):
    linha = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    with _trava:
        print(linha, flush=True)
        with open(os.path.join(SAIDA, "coleta.log"), "a", encoding="utf-8") as f:
            f.write(linha + "\n")


# --------------------------------------------------------------------------- rede
def baixar(url):
    """Devolve (status, texto). status 0 = falha de rede depois de todas as tentativas."""
    status, texto = 0, ""
    for tentativa in range(TENTATIVAS):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": AGENTE, "Accept-Encoding": "gzip",
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=30) as r:
                dados = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    dados = gzip.decompress(dados)
                return r.status, dados.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            status = e.code
            if status == 404:
                return 404, ""
            texto = "HTTP %d" % status
        except Exception as e:                      # timeout, conexao, etc.
            status, texto = 0, repr(e)
        time.sleep(2 * (tentativa + 1) ** 2)        # 2, 8, 18, 32 s
    return status, texto


# --------------------------------------------------------------------------- progresso
def ler_jsonl(caminho):
    itens = []
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    try:
                        itens.append(json.loads(linha))
                    except ValueError:
                        pass                        # linha cortada por interrupcao
    return itens


def anexar_jsonl(caminho, item):
    with _trava:
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def em_paralelo(funcao, itens, rotulo):
    """Roda funcao(item) em THREADS threads; para se houver muitas falhas seguidas."""
    estado = {"feitos": 0, "falhas_seguidas": 0, "parar": False}
    inicio, total = time.time(), len(itens)

    def tarefa(item):
        if estado["parar"]:
            return
        ok = funcao(item)
        with _trava:
            estado["feitos"] += 1
            estado["falhas_seguidas"] = 0 if ok else estado["falhas_seguidas"] + 1
            if estado["falhas_seguidas"] >= MAX_BLOQUEIOS:
                estado["parar"] = True
            n = estado["feitos"]
        if n % 250 == 0 or n == total:
            resta = (time.time() - inicio) / n * (total - n)
            log("%s: %d/%d (faltam ~%d min)" % (rotulo, n, total, resta / 60 + 1))
        time.sleep(PAUSA)

    with ThreadPoolExecutor(THREADS) as pool:
        list(pool.map(tarefa, itens))
    if estado["parar"]:
        raise Bloqueado("%s: %d falhas seguidas; o site pode estar bloqueando o acesso. "
                        "Espere alguns minutos e rode o script de novo (ele retoma de onde parou)."
                        % (rotulo, MAX_BLOQUEIOS))


# --------------------------------------------------------------------------- Metacritic
def mc_url_lista(offset, limite, ordem="-metaScore", ano_min=1900, ano_max=None):
    if ano_max is None:
        ano_max = time.localtime().tm_year + 1
    return ("%s/finder/metacritic/web?sortBy=%s&productType=games&page=1"
            "&releaseYearMin=%d&releaseYearMax=%d&offset=%d&limit=%d&apiKey=%s"
            % (MC_BASE, ordem, ano_min, ano_max, offset, limite, MC_CHAVE))


def mc_pagina(offset, limite, **filtro):
    """Uma pagina do localizador: devolve (itens, total)."""
    status, texto = baixar(mc_url_lista(offset, limite, **filtro))
    if status != 200:
        raise Bloqueado("Metacritic (lista): status %s %s" % (status, texto[:100]))
    dados = json.loads(texto)["data"]
    return dados.get("items", []), dados.get("totalResults", 0)


def mc_listar(offsets=None, limite=50):
    """Lista de jogos (id, slug, title) pelo localizador do Metacritic.

    O localizador pagina uma lista ordenada por nota; como ha muitos empates, a
    mesma entrada pode se repetir entre paginas e outra ficar de fora. Por isso a
    lista e percorrida em duas passagens (geral por nota e ano a ano) e o
    resultado e a uniao delas. So entram jogos com nota da critica.
    """
    if offsets is not None:                         # modo teste: paginas avulsas
        jogos = []
        for offset in offsets:
            itens, total = mc_pagina(offset, limite)
            jogos += [{"id": it.get("id"), "slug": it.get("slug"), "title": it.get("title")}
                      for it in itens]
            time.sleep(PAUSA)
        log("Metacritic: %d jogos na lista (total informado pelo site: %s)" % (len(jogos), total))
        return jogos

    arq = os.path.join(PARCIAL, "mc_lista.jsonl")
    linhas = ler_jsonl(arq)
    # Uma versao anterior fazia uma terceira passagem, ordenada por data, que traz
    # tambem os jogos sem nota da critica (mais de 180 mil). Tudo o que foi gravado
    # depois do fim da passagem ano a ano e descartado.
    fim_ano = [i for i, x in enumerate(linhas) if x.get("fim") and x.get("passagem") == "ano"]
    if fim_ano and len(linhas) > fim_ano[0] + 1:
        descartadas = len(linhas) - fim_ano[0] - 1
        linhas = linhas[:fim_ano[0] + 1]
        with open(arq, "w", encoding="utf-8") as f:
            for x in linhas:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        log("Metacritic lista: %d entradas da passagem por data descartadas" % descartadas)
    feitas = {x["passagem"] for x in linhas if x.get("fim") and "passagem" in x}
    if any(x.get("fim") and "passagem" not in x for x in linhas):
        feitas.add("nota")                          # marcador da primeira versao do script
    jogos = {}
    for x in linhas:
        if not x.get("fim") and x.get("id") is not None:
            jogos.setdefault(x["id"], x)

    def passagem(nome, **filtro):
        offset, novos = 0, 0
        while True:
            itens, total = mc_pagina(offset, limite, **filtro)
            for it in itens:
                jogo = {"id": it.get("id"), "slug": it.get("slug"), "title": it.get("title")}
                if jogo["id"] is not None and jogo["id"] not in jogos:
                    jogos[jogo["id"]] = jogo
                    anexar_jsonl(arq, jogo)
                    novos += 1
            offset += limite
            if offset % 1000 == 0:
                log("Metacritic lista (%s): %d/%d" % (nome, min(offset, total), total))
            if not itens or offset >= total:
                return novos
            time.sleep(PAUSA)

    ano_final = time.localtime().tm_year + 1
    if "nota" not in feitas:
        n = passagem("por nota")
        anexar_jsonl(arq, {"fim": True, "passagem": "nota"})
        log("Metacritic lista por nota: %d jogos novos" % n)
    if "ano" not in feitas:
        n = passagem("ate 1994", ano_min=1900, ano_max=1994)
        for ano in range(1995, ano_final + 1):
            n += passagem(str(ano), ano_min=ano, ano_max=ano)
        anexar_jsonl(arq, {"fim": True, "passagem": "ano"})
        log("Metacritic lista ano a ano: %d jogos novos" % n)
    log("Metacritic: %d jogos distintos na lista" % len(jogos))
    return list(jogos.values())


def mc_extrair(pagina):
    """Monta a linha do games.csv a partir da resposta do endpoint 'composer'."""
    comps = pagina.get("components", [])
    por_nome = {}
    for c in comps:
        por_nome.setdefault((c.get("meta") or {}).get("componentName"), c)

    def item(nome):
        return ((por_nome.get(nome) or {}).get("data") or {}).get("item") or {}

    prod = item("product") or ((comps[0].get("data") or {}).get("item") or {})
    critica, usuarios = item("critic-score-summary"), item("user-score-summary")
    plats = [p for p in (prod.get("platforms") or [])
             if (p.get("criticScoreSummary") or {}).get("score") is not None and p.get("name")]
    empresas = (prod.get("production") or {}).get("companies") or []
    nota_u = usuarios.get("score")

    def nomes(tipo):
        return ",".join(e["name"] for e in empresas
                        if tipo in (e.get("typeName") or "") and e.get("name"))

    return {
        "id": prod.get("id"), "title": prod.get("title"),
        "releaseDate": prod.get("releaseDate"), "rating": prod.get("rating"),
        "genres": ",".join(g["name"] for g in (prod.get("genres") or []) if g.get("name")),
        "description": prod.get("description"),
        "platforms": ",".join(p["name"] for p in plats),
        "metascore": critica.get("score"), "metascore_count": critica.get("reviewCount"),
        "metascore_sentiment": critica.get("sentiment"),
        "userscore": round(nota_u * 10) if isinstance(nota_u, (int, float)) else None,
        "userscore_count": usuarios.get("reviewCount"),
        "userscore_sentiment": usuarios.get("sentiment"),
        "platform_metascores": ",".join(str(p["criticScoreSummary"]["score"]) for p in plats),
        "developer": nomes("Developer"), "publisher": nomes("Publisher"),
    }


def mc_detalhar(jogos, arq, guardar_bruto=None):
    feitos = {x["id"] for x in ler_jsonl(arq)}
    faltam = [j for j in jogos if j["id"] not in feitos]
    log("Metacritic detalhes: %d ja coletados, %d a coletar" % (len(feitos), len(faltam)))

    def um(jogo):
        url = ("%s/composer/metacritic/pages/games/%s/web?filter=all&sort=date&apiKey=%s"
               % (MC_BASE, jogo["slug"], MC_CHAVE))
        status, texto = baixar(url)
        if status == 404:
            log("Metacritic 404: %s" % jogo["slug"])
            anexar_jsonl(arq, {"id": jogo["id"], "erro": 404})
            return True
        if status != 200:
            log("Metacritic falha %s em %s: %s" % (status, jogo["slug"], texto[:80]))
            return False
        try:
            pagina = json.loads(texto)
            linha = mc_extrair(pagina)
            if linha["id"] is None:
                raise ValueError("sem id")
        except Exception as e:
            log("Metacritic erro de leitura em %s: %r" % (jogo["slug"], e))
            anexar_jsonl(arq, {"id": jogo["id"], "erro": "leitura"})
            return True
        if guardar_bruto is not None and len(guardar_bruto) < 2:
            guardar_bruto.append([{"meta": c.get("meta"),
                                   "item": (c.get("data") or {}).get("item")}
                                  for c in pagina.get("components", [])
                                  if (c.get("meta") or {}).get("componentName") in
                                  ("product", "critic-score-summary", "user-score-summary")])
        anexar_jsonl(arq, {"id": jogo["id"], "linha": linha})
        return True

    em_paralelo(um, faltam, "Metacritic detalhes")
    return [x["linha"] for x in ler_jsonl(arq) if "linha" in x]


# --------------------------------------------------------------------------- HowLongToBeat
_RE_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def hltb_um(game_id, arq, diag=None):
    """Baixa um jogo. Grava {"id", "jogo"} ou {"id", "inexistente"}. Devolve False se falhou."""
    status, texto = baixar(HLTB_BASE + str(game_id))
    if diag is not None:
        with _trava:
            diag.append((game_id, status, len(texto)))
    if status == 404:
        anexar_jsonl(arq, {"id": game_id, "inexistente": True})
        return True
    if status != 200:
        log("HLTB falha %s no id %s: %s" % (status, game_id, texto[:80]))
        return False
    try:
        m = _RE_NEXT.search(texto)
        dados = json.loads(m.group(1))["props"]["pageProps"]["game"]["data"]
        jogo = dados["game"][0]
    except Exception:
        # pagina sem os dados do jogo: ID inexistente (ou pagina de bloqueio)
        if "__NEXT_DATA__" not in texto:
            log("HLTB id %s: pagina sem dados (possivel bloqueio), %d bytes" % (game_id, len(texto)))
            return False
        anexar_jsonl(arq, {"id": game_id, "inexistente": True})
        return True
    anexar_jsonl(arq, {"id": game_id, "jogo": jogo})
    return "jogo"


_DE = "ÀÁÂÃÄÅàáâãäåÈÉÊËèéêëÌÍÎÏìíîïÒÓÔÕÖòóôõöÙÚÛÜùúûüÇçÑñŌōŪū"
_PARA = "AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCcNnOoUu"
_TABELA = str.maketrans(_DE, _PARA)


def normaliza(x):
    """Mesma chave de juncao do notebook preparar_dados_jogos.ipynb."""
    x = (x or "").translate(_TABELA).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", x).strip()


def ler_hltb_antigo():
    """Devolve (lista de (id, chave), maior id) de dados/hltb_ids.csv; ([], 0) se nao existir."""
    pares, maior = [], 0
    if not os.path.exists(ARQ_IDS_HLTB):
        return pares, maior
    with open(ARQ_IDS_HLTB, encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            try:
                gid = int(linha["game_id"])
            except (ValueError, TypeError, KeyError):
                continue
            maior = max(maior, gid)
            pares.append((gid, normaliza(linha.get("game_name"))))
    return pares, maior


def atualizar_ids_hltb(jogos):
    """Acrescenta a dados/hltb_ids.csv os jogos coletados (id e nome)."""
    nomes = {}
    if os.path.exists(ARQ_IDS_HLTB):
        with open(ARQ_IDS_HLTB, encoding="utf-8", newline="") as f:
            for linha in csv.DictReader(f):
                try:
                    nomes[int(linha["game_id"])] = linha.get("game_name") or ""
                except (ValueError, TypeError, KeyError):
                    pass
    antes = len(nomes)
    for j in jogos:
        if j.get("game_id") is not None:
            nomes[int(j["game_id"])] = j.get("game_name") or ""
    os.makedirs(os.path.dirname(ARQ_IDS_HLTB), exist_ok=True)
    with open(ARQ_IDS_HLTB, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["game_id", "game_name"])
        for gid in sorted(nomes):
            w.writerow([gid, nomes[gid]])
    log("dados/hltb_ids.csv: %d IDs (%d novos)" % (len(nomes), len(nomes) - antes))


def ids_da_base_atual():
    ids = []
    if os.path.exists(ARQ_BASE_ATUAL):
        with open(ARQ_BASE_ATUAL, encoding="utf-8", newline="") as f:
            for linha in csv.DictReader(f):
                ids.append((int(linha["id_metacritic"]), int(linha["id_hltb"])))
    return ids


def hltb_coletar(linhas_mc, completo):
    arq = os.path.join(PARCIAL, "hltb.jsonl")
    antigos, maior_antigo = ler_hltb_antigo()
    log("HLTB conhecidos: %d IDs em dados/hltb_ids.csv, maior ID %d" % (len(antigos), maior_antigo))

    if completo:
        alvos = set(range(1, maior_antigo + 1))
    else:
        chaves_mc = {normaliza(re.sub(r"\s*\((19|20)[0-9]{2}\)\s*$", "", l["title"] or ""))
                     for l in linhas_mc}
        alvos = {gid for gid, chave in antigos if chave and chave in chaves_mc}
        alvos |= {h for _, h in ids_da_base_atual()}
    feitos = {x["id"] for x in ler_jsonl(arq)}
    faltam = sorted(alvos - feitos)
    log("HLTB (IDs ja conhecidos): %d alvos, %d a coletar" % (len(alvos), len(faltam)))
    em_paralelo(lambda g: hltb_um(g, arq), faltam, "HLTB conhecidos")

    # IDs novos: avanca em lotes ate MAX_404_SEGUIDOS inexistentes seguidos
    achado = {x["id"]: ("jogo" in x) for x in ler_jsonl(arq) if x["id"] > maior_antigo}
    proximo, seguidos = maior_antigo + 1, 0
    while seguidos < MAX_404_SEGUIDOS:
        lote = list(range(proximo, proximo + 200))

        def um(g):
            ok = hltb_um(g, arq)
            if ok:
                achado[g] = ok == "jogo"
            return ok

        em_paralelo(um, [g for g in lote if g not in achado],
                    "HLTB novos (a partir de %d)" % proximo)
        for g in lote:
            seguidos = 0 if achado.get(g) else seguidos + 1
            if seguidos >= MAX_404_SEGUIDOS:
                break
        proximo += 200
    log("HLTB: varredura de IDs novos encerrada no ID %d" % proximo)
    return [x["jogo"] for x in ler_jsonl(arq) if "jogo" in x]


# --------------------------------------------------------------------------- gravacao
def gravar_mc(linhas, caminho):
    vistos, unicas = set(), []
    for l in linhas:
        if l["id"] not in vistos:
            vistos.add(l["id"])
            unicas.append(l)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_MC)
        w.writeheader()
        w.writerows(unicas)
    log("Gravado %s (%d jogos)" % (caminho, len(unicas)))


def gravar_hltb(jogos, caminho):
    vistos, unicos, colunas = set(), [], []
    for j in jogos:
        if j.get("game_id") in vistos:
            continue
        vistos.add(j.get("game_id"))
        unicos.append(j)
        for k in j:
            if k not in colunas:
                colunas.append(k)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["game_" + c for c in colunas])
        for j in unicos:
            w.writerow(["" if j.get(c) is None else
                        (json.dumps(j[c], ensure_ascii=False) if isinstance(j[c], (dict, list)) else j[c])
                        for c in colunas])
    log("Gravado %s (%d registros)" % (caminho, len(unicos)))


# --------------------------------------------------------------------------- modos
def modo_teste():
    rel = []
    arq_mc = os.path.join(PARCIAL, "teste_mc.jsonl")
    arq_h = os.path.join(PARCIAL, "teste_hltb.jsonl")
    for a in (arq_mc, arq_h):
        if os.path.exists(a):
            os.remove(a)

    # Metacritic: 17 jogos de tres pontos diferentes do ranking
    linhas_mc, bruto = [], []
    try:
        t0 = time.time()
        jogos = mc_listar(offsets=[0, 4000, 9000], limite=17)
        linhas_mc = mc_detalhar(jogos, arq_mc, guardar_bruto=bruto)
        dt = time.time() - t0
        rel.append("METACRITIC: OK - %d de %d jogos em %.0f s (%.2f s por jogo)"
                   % (len(linhas_mc), len(jogos), dt, dt / max(1, len(jogos))))
    except Exception as e:
        rel.append("METACRITIC: FALHOU - %r" % (e,))
    gravar_mc(linhas_mc, os.path.join(SAIDA, "teste_games.csv"))
    with open(os.path.join(SAIDA, "teste_amostra_metacritic.json"), "w", encoding="utf-8") as f:
        json.dump(bruto, f, ensure_ascii=False, indent=1)

    # HLTB: os jogos acima que estao na base atual + outros ate 50 + alguns IDs novos
    diag, jogos_h = [], []
    try:
        base = ids_da_base_atual()
        mapa = dict(base)
        ids = [mapa[l["id"]] for l in linhas_mc if l["id"] in mapa]
        passo = max(1, len(base) // 60)
        if not ids and not base:
            ids = list(range(1, 51))
        for _, h in base[::passo]:
            if len(ids) >= 50:
                break
            if h not in ids:
                ids.append(h)
        _, maior = ler_hltb_antigo()
        ids += [maior + k for k in (1, 2, 3, 500, 2000, 5000, 10000, 20000, 40000)] + [99999999]
        t0 = time.time()
        em_paralelo(lambda g: hltb_um(g, arq_h, diag), ids, "HLTB teste")
        dt = time.time() - t0
        res = ler_jsonl(arq_h)
        jogos_h = [x["jogo"] for x in res if "jogo" in x]
        rel.append("HLTB: %d encontrados, %d inexistentes, %d sem resposta, em %.0f s (%.2f s por ID)"
                   % (len(jogos_h), sum(1 for x in res if x.get("inexistente")),
                      len(ids) - len(res), dt, dt / len(ids)))
        rel.append("HLTB maior ID conhecido: %d" % maior)
        rel.append("HLTB IDs novos testados (id, status, bytes): %s"
                   % sorted(d for d in diag if d[0] > maior))
        rel.append("HLTB status por requisicao: %s"
                   % sorted({s: sum(1 for d in diag if d[1] == s) for s in {d[1] for d in diag}}.items()))
    except Exception as e:
        rel.append("HLTB: FALHOU - %r" % (e,))
    gravar_hltb(jogos_h, os.path.join(SAIDA, "teste_hltb_data.csv"))

    rel.append("Python %s em %s" % (sys.version.split()[0], sys.platform))
    with open(os.path.join(SAIDA, "teste_relatorio.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(rel) + "\n")
    print("\n===== RESULTADO DO TESTE =====")
    print("\n".join(rel))
    print("\nTeste concluido. Os arquivos estao na pasta Coleta.")


def modo_completo(hltb_completo):
    log("Inicio da coleta completa")
    jogos = mc_listar()
    linhas_mc = mc_detalhar(jogos, os.path.join(PARCIAL, "mc_detalhes.jsonl"))
    gravar_mc(linhas_mc, os.path.join(SAIDA, "games.csv"))
    jogos_h = hltb_coletar(linhas_mc, hltb_completo)
    gravar_hltb(jogos_h, os.path.join(SAIDA, "hltb_data.csv"))
    atualizar_ids_hltb(jogos_h)
    log("Coleta completa concluida")
    print("\nColeta concluida. Agora rode: python montar_base.py")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    os.makedirs(PARCIAL, exist_ok=True)
    try:
        if "teste" in sys.argv[1:]:
            modo_teste()
        else:
            modo_completo("--hltb-completo" in sys.argv[1:])
    except Bloqueado as e:
        log("INTERROMPIDO: %s" % e)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrompido. Rode o mesmo comando de novo para retomar de onde parou.")
        sys.exit(1)
