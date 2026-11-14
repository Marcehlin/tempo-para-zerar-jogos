# Tempo para zerar jogos × notas do Metacritic

Base de dados para modelar o **tempo médio para terminar a história principal** de um
jogo eletrônico (segundo o [HowLongToBeat](https://howlongtobeat.com)) em função de
características do jogo e das suas notas no [Metacritic](https://www.metacritic.com).
Foi montada para um trabalho de Modelos Lineares Generalizados (MLG).

Este repositório traz a base pronta e os scripts que a coletam e montam do zero.

- **Base:** [`dados/tempo-para-zerar-jogos.csv`](dados/tempo-para-zerar-jogos.csv), com 7.094 jogos e 17 colunas, sem valores faltantes.
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
| `pc` | 1 se o jogo saiu para PC |
| `desenvolvedora` | estúdio que fez o jogo (o primeiro listado no Metacritic) |
| `regiao_empresa` | região da empresa dona do estúdio na época do lançamento: `america_do_norte`, `europa`, `japao`, `outros` ou `desconhecido` |

Para ler no R:

```r
dados <- read.csv("dados/tempo-para-zerar-jogos.csv", stringsAsFactors = TRUE)
```

## Como atualizar a base

Só é preciso Python 3 (nenhum pacote extra).

```
python coletar_dados.py teste    # opcional: amostra de ~50 jogos, 1 a 2 minutos
python coletar_dados.py          # coleta completa
python montar_base.py            # gera dados/tempo-para-zerar-jogos.csv
```

A coleta completa faz cerca de 15 mil consultas ao Metacritic e de 15 a 50 mil ao
HowLongToBeat, com 4 consultas simultâneas e pausa entre elas. Leva algumas horas. Pode
ser interrompida: o mesmo comando retoma de onde parou (o progresso fica em
`Coleta/parcial/`). Os dados brutos ficam na pasta `Coleta/`, que não entra no
repositório.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `coletar_dados.py` | coleta do Metacritic e do HowLongToBeat |
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
- A maior parte do código foi escrita pelo Claude (Anthropic), a partir das regras de
  junção, filtro e classificação definidas para o trabalho.
