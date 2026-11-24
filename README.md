# Tempo para zerar jogos × notas do Metacritic

*[English version](README.en.md)*

Base de dados para modelar o **tempo médio para terminar a história principal** de um
jogo eletrônico (segundo o [HowLongToBeat](https://howlongtobeat.com)) em função de
características do jogo e das suas notas no [Metacritic](https://www.metacritic.com).
Foi montada para um trabalho de Modelos Lineares Generalizados (MLG).

Este repositório traz a base pronta e os scripts que a coletam e montam do zero.

- **Base:** [`dados/tempo-para-zerar-jogos.csv`](dados/tempo-para-zerar-jogos.csv), com 7.094 jogos e 19 colunas. Só as duas colunas de tamanho têm valores faltantes (campo vazio).
- **Coleta:** 13 e 14 de novembro de 2026.

## Colunas de `dados/tempo-para-zerar-jogos.csv`

| Coluna | Descrição |
|---|---|
| `id_metacritic` | identificador do jogo no Metacritic |
| `id_hltb` | identificador do jogo no HowLongToBeat |
| `titulo` | título no Metacritic |
| `tempo_medio_h` | **resposta**: média dos tempos relatados para: terminar a história principal/ completar objetivos principais / aproveitar o suficiente do jogo, em horas |
| `n_relatos` | número de relatos que formaram essa média (mínimo 5) |
| `metascore` | nota da crítica, de 0 a 100 |
| `userscore` | nota dos usuários, de 0 a 100 |
| `n_criticas` | número de resenhas da crítica |
| `n_avaliacoes_usuarios` | número de avaliações de usuários |
| `ano` | ano de lançamento no Metacritic |
| `genero` | gênero agrupado em 10 categorias mais `Outros` |
| `genero_metacritic` | gênero original do Metacritic |
| `classificacao` | classificação etária ESRB: `E`, `E10+`, `T`, `M` ou `Sem classificacao` |
| `n_plataformas` | número de plataformas com nota da crítica |
| `pc` | 1 se o jogo saiu para PC em algum momento (inclui ports e remasters tardios): PC na lista do Metacritic ou do HowLongToBeat, ou ID da Steam |
| `desenvolvedora` | estúdio que fez o jogo (o primeiro listado no Metacritic) |
| `regiao_empresa` | região da empresa dona do estúdio na época do lançamento: `america_do_norte`, `europa`, `japao`, `outros` ou `desconhecido` |
| `tamanho_gb` | espaço que o jogo ocupa, em GB (vazio quando não há dado; ver "Tamanho em armazenamento") |
| `plataforma_tamanho` | plataforma de onde veio o tamanho (`PC` = requisito da Steam; as demais = catálogo do console) |

Para ler no R:

```r
dados <- read.csv("dados/tempo-para-zerar-jogos.csv", stringsAsFactors = TRUE, na.strings = "")
```

## Como atualizar a base

Só é preciso Python 3 (nenhum pacote extra).

```
python coletar_dados.py teste       # opcional: amostra de ~50 jogos, 1 a 2 minutos
python coletar_dados.py             # coleta completa
python coletar_tamanhos.py teste    # opcional: catálogos de console + 30 jogos da Steam
python coletar_tamanhos.py          # tamanho em armazenamento
python montar_base.py               # gera dados/tempo-para-zerar-jogos.csv
```

A coleta completa faz cerca de 15 mil consultas ao Metacritic e de 15 a 50 mil ao
HowLongToBeat, com 4 consultas simultâneas e pausa entre elas. Leva algumas horas. Pode
ser interrompida: o mesmo comando retoma de onde parou (o progresso fica em
`Coleta/parcial/`). Os dados brutos ficam na pasta `Coleta/`, que não entra no
repositório.

A coleta de tamanhos baixa os catálogos de console (cerca de 110 MB, poucos minutos) e
consulta a Steam um jogo por vez, com pausa de 1,5 s por causa do limite de acessos da
loja: perto de 4.500 consultas, umas 2 horas. Também pode ser interrompida e retomada.
Sem ela, `montar_base.py` funciona normalmente e deixa as duas colunas de tamanho vazias.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `coletar_dados.py` | coleta do Metacritic e do HowLongToBeat |
| `coletar_tamanhos.py` | tamanho em armazenamento (catálogos de console e Steam) |
| `montar_base.py` | junção das duas fontes, filtros e construção das variáveis |
| `dados/tempo-para-zerar-jogos.csv` | base final |
| `dados/estudios_regiao.csv` | região da empresa dona de cada estúdio |
| `dados/hltb_ids.csv` | IDs e nomes de jogos já conhecidos no HowLongToBeat, usados para dirigir a coleta |

## Como a base é montada

1. **Chave de junção.** As duas fontes não compartilham identificador, então a junção é
   pelo nome do jogo, normalizado: sem acentos, em minúsculas, `&` vira `and` e a
   pontuação vira espaço. O ano que o Metacritic acrescenta a títulos homônimos, como em
   `God of War (2005)`, é retirado antes.
2. **Filtro do HowLongToBeat.** Ficam só registros do tipo `game` (saem DLCs, compilações,
   mods etc.), com data de lançamento conhecida e pelo menos 5 relatos de tempo da
   história principal.
3. **Validação pelo ano.** Um par só é aceito se os anos de lançamento nas duas fontes
   diferem em no máximo 1. A correspondência final é 1 para 1: em caso de duplicata fica
   o par de ano mais próximo e, no empate, o registro com mais relatos (HowLongToBeat) ou
   com mais avaliações de usuários (Metacritic).
4. **Limpeza.** Saem jogos sem nota de usuários, sem metascore, sem plataforma, sem
   gênero ou desenvolvedora, e as compilações.

Na coleta de novembro de 2026, dos 14.464 jogos do Metacritic, 7.251 formaram par e
7.094 ficaram na base.

### Gênero

Os gêneros do Metacritic são agrupados em `RPG`, `Acao-Aventura`, `Aventura`, `Tiro`,
`Plataforma`, `Luta`, `Estrategia`, `Simulacao`, `Puzzle`, `Esporte-Corrida` e `Outros`.
O mapeamento completo está em `GRUPOS`, no `montar_base.py`; o gênero original fica em
`genero_metacritic` para quem quiser agrupar de outro jeito.

### Classificação etária

`K-A` é a sigla antiga de `E`; `AO` foi unido a `M`; `RP` (pendente) e ausente viram
`Sem classificacao`.

### Região da empresa

Nenhuma das fontes traz país. A tabela `dados/estudios_regiao.csv` atribui a cada
estúdio a região da **empresa dona na época do lançamento**:

- estúdio independente: vale o país do próprio estúdio;
- estúdio de um grupo: vale a sede do grupo (Ubisoft Montreal é `europa`; Naughty Dog é
  `japao`, por pertencer à Sony);
- estúdio que mudou de dono: há uma linha por período (coluna `a_partir_de`) e vale a do
  ano de lançamento do jogo;
- participações minoritárias e acionistas financeiros não contam como dono;
- estúdio não identificado fica como `desconhecido`.

As regiões são `america_do_norte` (EUA e Canadá), `europa` (inclui Rússia e Ucrânia),
`japao` e `outros` (resto da Ásia, Oceania, América Latina, África, Oriente Médio e
Turquia). Para corrigir uma classificação, edite a tabela e rode `python montar_base.py`.

### Tamanho em armazenamento

Nenhuma fonte única cobre todas as plataformas, então são usadas duas:

| Origem | Plataformas | O que mede |
|---|---|---|
| Catálogos [Redump e No-Intro](https://github.com/libretro/libretro-database) | PlayStation, PS2, PS3, PSP, PS Vita, Dreamcast, Nintendo 64, Game Boy Advance, DS, 3DS | tamanho da imagem do disco, da ROM do cartucho ou do pacote digital (Vita e 3DS digital) |
| Catálogo da eShop, [titledb](https://github.com/blawar/titledb) | Nintendo Switch | tamanho do download |
| API da loja Steam | PC | espaço livre exigido nos requisitos mínimos, quando o HowLongToBeat traz o ID da Steam do jogo |

- **Junção:** nos catálogos de console, pelo nome normalizado, como na junção principal.
  Entre as versões de um mesmo jogo vale a dos EUA (depois mundial, Europa, outras,
  Japão). Jogos de vários discos têm os discos somados. Demos, DLC, temas, protótipos e
  relançamentos (Virtual Console etc.) ficam de fora.
- **Jogos multiplataforma:** vale o tamanho na plataforma mais antiga, entre os consoles
  em que o jogo saiu e que têm dado. A Steam só é usada quando não há tamanho de console.
- **Plataformas sem dado:** PS4, PS5, Xbox One e Series, Switch 2 (sem catálogo aberto),
  Xbox 360, GameCube, Wii (a imagem de disco tem tamanho praticamente fixo) e Wii U.
  Jogos exclusivos delas ficam sem tamanho, a menos que tenham ID da Steam.

## Limitações

- **Junção por nome.** Jogos com grafias diferentes nas duas fontes não formam par, e
  cerca de metade dos jogos do Metacritic fica de fora por isso ou por falta de relatos.
- **Média de relatos voluntários.** O tempo vem de jogadores que escolheram relatar; jogos
  com poucos relatos têm média instável (`n_relatos` pode servir de peso ou de filtro).
- **Versão principal no Metacritic.** Ano, desenvolvedora e contagens são os da versão que
  o Metacritic mostra como principal, que pode não ser a do lançamento original.
- **Tabela de regiões.** Parte foi montada à mão e parte (367 estúdios, acrescentados em
  novembro de 2026) foi proposta com ajuda de IA e só parcialmente verificada. Correções
  são bem-vindas.
- **Tamanho mede coisas diferentes conforme a origem.** Nos consoles é o arquivo real; nos
  cartuchos de DS e 3DS é a capacidade do cartucho, que vem em potências de 2. Na Steam é
  o espaço declarado pelo desenvolvedor, arredondado, na versão atual da página: jogos que
  receberam atualizações grandes aparecem maiores do que eram no lançamento. A ordem de
  grandeza também muda muito entre gerações (megabytes nos cartuchos, dezenas de gigabytes
  no PC), então o tamanho costuma entrar no modelo em escala log e junto com
  `plataforma_tamanho`.
- **Faltantes de tamanho não são aleatórios.** Concentram-se em exclusivos de PlayStation 4
  e 5, Xbox e consoles de mesa da Nintendo. Ajustar um modelo só com os jogos que têm
  tamanho muda a população estudada.
- **HowLongToBeat parcial.** A coleta visita os IDs conhecidos cujo nome coincide com o de
  algum jogo do Metacritic e todos os IDs novos; um jogo antigo renomeado no site pode
  não ser revisitado. A opção `--hltb-completo` visita todos.

## Créditos

- Os dados vêm do [Metacritic](https://www.metacritic.com) e do
  [HowLongToBeat](https://howlongtobeat.com). Este projeto não tem vínculo com nenhum dos
  dois, e o uso dos dados está sujeito aos termos de cada site.
- A coleta se baseia na abordagem de dois projetos, que também serviram de ponto de
  partida para a primeira versão da base (via Kaggle):
  - [davutbayik/metacritic-backend-scraper](https://github.com/davutbayik/metacritic-backend-scraper)
    ([dados no Kaggle](https://www.kaggle.com/datasets/davutb/metacritic-games/data));
  - [zaireali649/howlongtobeat-scraper](https://github.com/zaireali649/howlongtobeat-scraper)
    ([dados no Kaggle](https://www.kaggle.com/datasets/zaireali/howlongtobeat-games-scraper-2162025)).
- Tamanhos: catálogos [Redump](http://redump.org) e [No-Intro](https://no-intro.org), na
  compilação do [libretro-database](https://github.com/libretro/libretro-database);
  [titledb](https://github.com/blawar/titledb) (eShop do Switch); e a loja
  [Steam](https://store.steampowered.com).
- A maior parte do código foi escrita pelo Claude (Anthropic), a partir das regras de
  junção, filtro e classificação definidas para o trabalho.
