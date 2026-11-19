"""Coleta o tamanho em armazenamento dos jogos da base.

Uso (na pasta do repositorio, depois de "python coletar_dados.py"):

    python coletar_tamanhos.py teste    # catalogos de console + 30 jogos da Steam
    python coletar_tamanhos.py          # coleta completa (pode ser interrompida e retomada)
    python montar_base.py               # grava as colunas tamanho_gb e plataforma_tamanho

So usa a biblioteca padrao do Python.

Fontes:
  1. Catalogos de console, com o tamanho real do arquivo do jogo:
     - Redump e No-Intro, via https://github.com/libretro/libretro-database
       (imagem do disco, ROM do cartucho ou pacote digital);
     - eShop do Switch, via https://github.com/blawar/titledb (arquivo US.en.json).
  2. Steam: espaco em disco exigido nos requisitos minimos de PC, pela API da loja
     (store.steampowered.com/api/appdetails), para os jogos que tem ID da Steam no
     HowLongToBeat.

Saidas (pasta Coleta/, que nao entra no repositorio):
    Coleta/tamanhos_console.csv   plataforma, chave, nome, tamanho_bytes, catalogo
    Coleta/tamanhos_steam.csv     steam_appid, situacao, tamanho_gb, requisitos
    Coleta/catalogos/             catalogos baixados (use --atualizar-catalogos para baixar de novo)
    Coleta/parcial/steam.jsonl    progresso da Steam (permite retomar)
    Coleta/tamanhos.log           registro de erros e andamento
"""

import csv
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import montar_base

PASTA = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(PASTA, "Coleta")
CATALOGOS = os.path.join(SAIDA, "catalogos")
PARCIAL = os.path.join(SAIDA, "parcial")
ARQ_STEAM = os.path.join(PARCIAL, "steam.jsonl")

AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

URL_LIBRETRO = "https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/"
URL_TITLEDB = "https://raw.githubusercontent.com/blawar/titledb/master/US.en.json"
URL_STEAM = "https://store.steampowered.com/api/appdetails?appids=%s&filters=basic&l=english&cc=us"

# A API da Steam limita acessos rapidos: uma consulta por vez, com pausa entre elas.
PAUSA_STEAM = 1.5          # segundos entre consultas
ESPERA_BLOQUEIO = 300      # segundos de espera quando a Steam recusa (HTTP 429/403)
MAX_BLOQUEIOS = 6          # recusas seguidas antes de desistir (rode de novo depois)

# (plataforma no Metacritic, arquivo em libretro-database/metadat, tipo).
# Em cada plataforma, o catalogo de midia fisica tem prioridade sobre o digital.
# Os catalogos digitais do PS3 e do PSP (PSN) ficam de fora: neles o jogo completo
# muitas vezes aparece como "Trial" destravado por chave, e a entrada "(PSN)" pode ser
# so um patch, entao o tamanho do jogo nao e identificavel com seguranca.
CATALOGOS_LIBRETRO = [
    ("PlayStation", "redump/Sony - PlayStation.dat", "fisico"),
    ("PlayStation 2", "redump/Sony - PlayStation 2.dat", "fisico"),
    ("PlayStation 3", "redump/Sony - PlayStation 3.dat", "fisico"),
    ("PSP", "redump/Sony - PlayStation Portable.dat", "fisico"),
    ("PlayStation Vita", "no-intro/Sony - PlayStation Vita.dat", "digital"),
    ("Dreamcast", "redump/Sega - Dreamcast.dat", "fisico"),
    ("Nintendo 64", "no-intro/Nintendo - Nintendo 64.dat", "fisico"),
    ("Game Boy Advance", "no-intro/Nintendo - Game Boy Advance.dat", "fisico"),
    ("DS", "no-intro/Nintendo - Nintendo DS.dat", "fisico"),
    ("3DS", "no-intro/Nintendo - Nintendo 3DS.dat", "fisico"),
    ("3DS", "no-intro/Nintendo - Nintendo 3DS (Digital).dat", "digital"),
]

# Entradas dos catalogos que nao sao o jogo completo (demos, DLC, relancamentos etc.)
_EXCLUIR = re.compile(
    r"\b(DLC|Demo|Trial|Taikenban|Theme|Avatar|Unlock Key|Proto|Beta|Update|Patch|Video|"
    r"Soundtrack|Kiosk|Sample|Save Data|Subscription|Virtual Console|Classics|PC ?Engine|PCE|"
    r"NES|Neo ?Geo|GBA|Broadcast|LodgeNet|PlayView|Controller|Unl|Pirate|Hack|Aftermarket|"
    r"Program|Debug|Promo|Bonus Disc|Add-On|Manual|Tech Demo)\b", re.I)
_DISCO = re.compile(r"\s*\((?:Disc|Disk|CD|DVD)\s*([^)]*)\)", re.I)
MIN_BYTES = 1024 ** 2      # entradas menores (arquivos de licenca da PSN etc.) nao sao o jogo
_ARTIGO = re.compile(r"^(.*?), (The|A|An)(\s+-\s+.*|\s*:.*|)$")


def log(msg):
    linha = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(linha, flush=True)
    with open(os.path.join(SAIDA, "tamanhos.log"), "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def baixar(url, tentativas=3):
    """Devolve (status, bytes). status 0 = falha de rede."""
    status, dados = 0, b""
    for tentativa in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=300) as r:
                dados = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    dados = gzip.decompress(dados)
                return r.status, dados
        except urllib.error.HTTPError as e:
            status = e.code
            if status in (403, 404, 429):
                return status, b""
        except Exception as e:
            status, dados = 0, repr(e).encode()
        time.sleep(3 * (tentativa + 1))
    return status, dados


# --------------------------------------------------------------------------- catalogos de console
def baixar_catalogo(url, nome_local, atualizar):
    caminho = os.path.join(CATALOGOS, nome_local)
    if os.path.exists(caminho) and not atualizar:
        return caminho
    status, dados = baixar(url)
    if status != 200 or not dados:
        log("Falha ao baixar %s (status %s)" % (url, status))
        return caminho if os.path.exists(caminho) else None
    with open(caminho + ".tmp", "wb") as f:
        f.write(dados)
    os.replace(caminho + ".tmp", caminho)
    log("Baixado %s (%.1f MB)" % (nome_local, len(dados) / 1024 ** 2))
    return caminho


def ler_dat(caminho):
    """Le um arquivo clrmamepro (.dat): devolve [(nome, soma dos tamanhos dos arquivos)]."""
    jogos, nome, total = [], None, 0
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            if linha.startswith("game ("):
                nome, total = None, 0
            elif linha.startswith("\tname \"") and nome is None:
                nome = linha.strip()[6:-1]
            elif linha.lstrip().startswith("rom ("):
                m = re.search(r"\bsize (\d+)", linha)
                if m:
                    total += int(m.group(1))
            elif linha.startswith(")") and nome is not None:
                jogos.append((nome, total))
                nome = None
    return jogos


def chave_catalogo(nome):
    """Chave de juncao a partir do nome no catalogo (mesma normalizacao da base)."""
    base = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", nome).strip()
    m = _ARTIGO.match(base)                        # "Legend of Zelda, The - X" -> "The Legend of Zelda - X"
    if m:
        base = "%s %s%s" % (m.group(2), m.group(1), m.group(3))
    return montar_base.normaliza(base)


def preferencia(nome):
    """Ordem de escolha entre versoes do mesmo jogo: EUA, mundo, Europa, outras, Japao."""
    etiquetas = re.findall(r"\(([^)]*)\)", nome)
    regiao = etiquetas[0] if etiquetas else ""
    if "USA" in regiao:
        r = 0
    elif "World" in regiao:
        r = 1
    elif "Europe" in regiao:
        r = 2
    elif "Japan" in regiao:
        r = 4
    else:
        r = 3
    return (r, len(etiquetas), nome)


def tamanhos_libretro(atualizar):
    """Devolve {(plataforma, chave): (bytes, nome, catalogo)}."""
    escolhido = {}
    for plataforma, arquivo, tipo in CATALOGOS_LIBRETRO:
        url = URL_LIBRETRO + urllib.parse.quote(arquivo)
        caminho = baixar_catalogo(url, arquivo.replace("/", " - "), atualizar)
        if caminho is None:
            continue
        # O catalogo repete o mesmo nome para reedicoes e formatos diferentes do mesmo
        # jogo: cada disco conta uma vez so (o maior). Discos diferentes do mesmo jogo,
        # como "X (USA) (Disc 1) (Parte A)" e "X (USA) (Disc 2) (Parte B)", sao somados.
        discos = {}
        for nome, tamanho in ler_dat(caminho):
            etiquetas = " ".join(re.findall(r"\(([^)]*)\)", nome))
            if tamanho < MIN_BYTES or _EXCLUIR.search(etiquetas):
                continue
            m = _DISCO.search(nome)
            versao, disco = (nome[:m.start()], m.group(1).strip()) if m else (nome, "")
            d = discos.setdefault(versao, {})
            d[disco] = max(d.get(disco, 0), tamanho)
        por_versao = {versao: sum(d.values()) for versao, d in discos.items()}
        candidatos = {}
        for versao, tamanho in por_versao.items():
            chave = chave_catalogo(versao)
            if chave:
                candidatos.setdefault(chave, []).append((preferencia(versao), versao, tamanho))
        n = 0
        for chave, lista in candidatos.items():
            if (plataforma, chave) in escolhido:   # ja veio de um catalogo de prioridade maior
                continue
            _, versao, tamanho = min(lista)
            escolhido[(plataforma, chave)] = (tamanho, versao, os.path.basename(arquivo))
            n += 1
        log("%-18s %-45s %6d jogos" % (plataforma, os.path.basename(arquivo), n))
    return escolhido


def tamanhos_switch(atualizar):
    """Devolve {("Nintendo Switch", chave): (bytes, nome, "titledb US.en.json")}."""
    caminho = baixar_catalogo(URL_TITLEDB, "titledb - US.en.json", atualizar)
    if caminho is None:
        return {}
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    candidatos = {}
    for item in dados.values():
        tid, nome, tamanho = item.get("id") or "", item.get("name") or "", item.get("size") or 0
        # so o jogo base (ID terminado em 000); DLC e atualizacoes tem outros finais
        if (not tid.endswith("000") or not tamanho or item.get("isDemo")
                or re.search(r"\b(demo|trial)\b", nome, re.I)):
            continue
        chave = montar_base.normaliza(nome)
        if chave:
            data = item.get("releaseDate") or 99999999
            candidatos.setdefault(chave, []).append((data, -int(tamanho), nome))
    escolhido = {}
    for chave, lista in candidatos.items():
        data, menos_tamanho, nome = min(lista)        # versao mais antiga; empate: a maior
        if -menos_tamanho < MIN_BYTES:
            continue
        escolhido[("Nintendo Switch", chave)] = (-menos_tamanho, nome, "titledb US.en.json")
    log("%-18s %-45s %6d jogos" % ("Nintendo Switch", "titledb US.en.json", len(escolhido)))
    return escolhido


def gravar_console(tabela):
    caminho = os.path.join(SAIDA, "tamanhos_console.csv")
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["plataforma", "chave", "nome", "tamanho_bytes", "catalogo"])
        for (plataforma, chave), (tamanho, nome, catalogo) in sorted(tabela.items()):
            w.writerow([plataforma, chave, nome, tamanho, catalogo])
    log("Gravado %s (%d linhas)" % (caminho, len(tabela)))


# --------------------------------------------------------------------------- Steam
_ROTULOS = "|".join([
    r"storage", r"hard\s*dis[ck]", r"hard\s*drive", r"hdd", r"hd\s*space", r"dis[ck]\s*space",
    r"free\s*space", r"almacenamiento", r"disco\s*duro", r"armazenamento", r"espace\s*disque",
    r"speicherplatz", r"festplatte", r"archiviazione", r"opslagruimte", r"miejsce\s*na\s*dysku",
    r"место\s*на\s*диске", r"存储空间", r"儲存空間", r"ストレージ", r"저장\s*공간"])
_NUMERO = r"(\d+(?:[.,]\d+)?)\s*\+?\s*(kb|mb|gb|tb|mo|go)\b"
# 1o: "4.5 GB free hard drive space"; 2o: "Storage: 4 GB"
_PADRAO1 = re.compile(_NUMERO + r"\s*(?:of\s*)?(?:free|available|uncompressed|"
                      r"(?:hard\s*dis[ck]|hard\s*drive|hd|dis[ck])\s*space(?!\s*:))", re.I)
_PADRAO2 = re.compile(r"(?:" + _ROTULOS + r")[^0-9]{0,40}?" + _NUMERO, re.I)
_FATOR = {"kb": 1 / 1024 ** 2, "mb": 1 / 1024, "mo": 1 / 1024, "gb": 1, "go": 1, "tb": 1024}


def extrai_gb(texto):
    """Espaco exigido, em GB, a partir do texto dos requisitos; None se nao achar."""
    m = _PADRAO1.search(texto) or _PADRAO2.search(texto)
    if not m:
        return None
    numero, unidade = m.group(1), m.group(2).lower()
    if re.fullmatch(r"\d{1,3},\d{3}", numero):     # "1,650 MB" = 1650 MB
        numero = numero.replace(",", "")
    gb = float(numero.replace(",", ".")) * _FATOR[unidade]
    return gb if 1 / 1024 <= gb <= 300 else None


def texto_requisitos(dados):
    """Texto dos requisitos minimos e recomendados de PC, sem HTML."""
    partes = []
    req = dados.get("pc_requirements")
    if isinstance(req, dict):
        for k in ("minimum", "recommended"):
            if req.get(k):
                t = html.unescape(re.sub(r"<[^>]+>", " ", req[k]))
                partes.append(re.sub(r"\s+", " ", t).strip())
    return " || ".join(partes)


def ler_progresso():
    feitos = {}
    if os.path.exists(ARQ_STEAM):
        with open(ARQ_STEAM, encoding="utf-8") as f:
            for linha in f:
                try:
                    x = json.loads(linha)
                    feitos[str(x["appid"])] = x
                except (ValueError, KeyError):
                    pass                            # linha cortada por interrupcao
    return feitos


def coletar_steam(appids):
    # se a execucao anterior caiu no meio de uma gravacao, fecha a linha cortada
    if os.path.exists(ARQ_STEAM) and os.path.getsize(ARQ_STEAM) > 0:
        with open(ARQ_STEAM, "rb") as f:
            f.seek(-1, os.SEEK_END)
            cortada = f.read(1) != b"\n"
        if cortada:
            with open(ARQ_STEAM, "a", encoding="utf-8") as f:
                f.write("\n")
    feitos = ler_progresso()
    faltam = [a for a in appids if a not in feitos]
    log("Steam: %d IDs, %d ja consultados, %d a consultar (~%d min)"
        % (len(appids), len(appids) - len(faltam), len(faltam), len(faltam) * (PAUSA_STEAM + 0.3) / 60 + 1))
    bloqueios, inicio = 0, time.time()
    for n, appid in enumerate(faltam, 1):
        while True:
            status, corpo = baixar(URL_STEAM % appid)
            if status == 200:
                bloqueios = 0
                break
            bloqueios += 1
            if bloqueios > MAX_BLOQUEIOS:
                log("Steam: muitas recusas seguidas (status %s). Rode de novo mais tarde; "
                    "o script retoma de onde parou." % status)
                return False
            log("Steam recusou (status %s); esperando %d s" % (status, ESPERA_BLOQUEIO))
            time.sleep(ESPERA_BLOQUEIO)
        try:
            resp = json.loads(corpo.decode("utf-8")).get(appid) or {}
        except ValueError:
            resp = {}
        if resp.get("success") and isinstance(resp.get("data"), dict):
            texto = texto_requisitos(resp["data"])
            item = {"appid": appid, "situacao": "ok" if texto else "sem requisitos", "requisitos": texto}
        else:
            item = {"appid": appid, "situacao": "indisponivel", "requisitos": ""}
        with open(ARQ_STEAM, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        if n % 100 == 0 or n == len(faltam):
            resta = (time.time() - inicio) / n * (len(faltam) - n)
            log("Steam: %d/%d (faltam ~%d min)" % (n, len(faltam), resta / 60 + 1))
        time.sleep(PAUSA_STEAM)
    return True


def gravar_steam(appids):
    feitos = ler_progresso()
    caminho = os.path.join(SAIDA, "tamanhos_steam.csv")
    n = 0
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["steam_appid", "situacao", "tamanho_gb", "requisitos"])
        for appid in sorted(feitos, key=int):
            if appid not in appids:
                continue
            x = feitos[appid]
            gb = extrai_gb(x["requisitos"]) if x["requisitos"] else None
            n += gb is not None
            w.writerow([appid, x["situacao"], "" if gb is None else "%.6g" % gb, x["requisitos"][:600]])
    log("Gravado %s (%d com espaco identificado)" % (caminho, n))
    return n


# --------------------------------------------------------------------------- principal
def jogos_da_base():
    """Linhas da base (com chave, plataformas e ID da Steam), calculadas como em montar_base.py."""
    linhas, _ = montar_base.montar(
        os.path.join(SAIDA, "games.csv"), os.path.join(SAIDA, "hltb_data.csv"),
        os.path.join(PASTA, "dados", "estudios_regiao.csv"))
    return linhas


def main():
    teste = "teste" in sys.argv[1:]
    atualizar = "--atualizar-catalogos" in sys.argv[1:]
    os.makedirs(CATALOGOS, exist_ok=True)
    os.makedirs(PARCIAL, exist_ok=True)
    log("Inicio da coleta de tamanhos" + (" (teste)" if teste else ""))

    linhas = jogos_da_base()
    log("Base: %d jogos" % len(linhas))

    console = tamanhos_libretro(atualizar)
    console.update(tamanhos_switch(atualizar))
    gravar_console(console)

    appids = []
    for l in linhas:
        if l["_steam"] and l["_steam"] not in appids:
            appids.append(l["_steam"])
    if teste:
        passo = max(1, len(appids) // 30)
        appids = appids[::passo][:30]
    completo = coletar_steam(appids)
    n_steam = gravar_steam(set(appids))

    # estimativa da cobertura, com a mesma regra de montar_base.py
    steam_gb = montar_base.ler_tamanhos_steam(os.path.join(SAIDA, "tamanhos_steam.csv"))
    tabela_console = montar_base.ler_tamanhos_console(os.path.join(SAIDA, "tamanhos_console.csv"))
    contagem = {}
    for l in linhas:
        _, plataforma = montar_base.escolher_tamanho(l, tabela_console, steam_gb)
        contagem[plataforma] = contagem.get(plataforma, 0) + 1
    print("\n===== RESULTADO =====")
    for plataforma, n in sorted(contagem.items(), key=lambda t: -t[1]):
        print("  %-18s %5d" % (plataforma or "(sem tamanho)", n))
    if teste:
        print("\nSteam: %d de %d IDs da amostra com espaco identificado." % (n_steam, len(appids)))
        print("Na amostra so 30 IDs da Steam foram consultados; o total de PC acima e parcial.")
        print("Teste concluido. Para a coleta completa: python coletar_tamanhos.py")
    elif completo:
        print("\nColeta concluida. Agora rode: python montar_base.py")
    else:
        print("\nColeta da Steam incompleta. Rode o mesmo comando mais tarde para continuar.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompido. Rode o mesmo comando de novo para retomar de onde parou.")
        sys.exit(1)
