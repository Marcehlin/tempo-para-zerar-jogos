# Time to beat video games × Metacritic scores

*[Versão em português](README.md)*

A dataset for modeling the **average time to finish the main story** of a video game
(according to [HowLongToBeat](https://howlongtobeat.com)) as a function of the game's
characteristics and its [Metacritic](https://www.metacritic.com) scores.
It was built for a Generalized Linear Models (GLM) course project.

This repository contains the ready-to-use dataset and the scripts that collect and build it from scratch.

- **Dataset:** [`dados/tempo-para-zerar-jogos.csv`](dados/tempo-para-zerar-jogos.csv), with 7,094 games and 19 columns. Only the two size columns have missing values (empty field).
- **Collected:** November 13–14, 2026.

## Columns of `dados/tempo-para-zerar-jogos.csv`

| Column | Description |
|---|---|
| `id_metacritic` | game identifier on Metacritic |
| `id_hltb` | game identifier on HowLongToBeat |
| `titulo` | title on Metacritic |
| `tempo_medio_h` | **response**: average of reported times to finish the main story / complete the main objectives / get enough out of the game, in hours |
| `n_relatos` | number of reports behind that average (minimum 5) |
| `metascore` | critic score, 0 to 100 |
| `userscore` | user score, 0 to 100 |
| `n_criticas` | number of critic reviews |
| `n_avaliacoes_usuarios` | number of user ratings |
| `ano` | release year on Metacritic |
| `genero` | genre grouped into 10 categories plus `Outros` (Other) |
| `genero_metacritic` | original Metacritic genre |
| `classificacao` | ESRB age rating: `E`, `E10+`, `T`, `M` or `Sem classificacao` (unrated) |
| `n_plataformas` | number of platforms with a critic score |
| `pc` | 1 if the game was released on PC |
| `desenvolvedora` | studio that made the game (the first one listed on Metacritic) |
| `regiao_empresa` | region of the studio's parent company at release time: `america_do_norte` (North America), `europa` (Europe), `japao` (Japan), `outros` (other) or `desconhecido` (unknown) |
| `tamanho_gb` | storage space the game takes, in GB (empty when there is no data; see "Storage size") |
| `plataforma_tamanho` | platform the size comes from (`PC` = Steam requirement; the others = console catalog) |

To load it in R:

```r
dados <- read.csv("dados/tempo-para-zerar-jogos.csv", stringsAsFactors = TRUE, na.strings = "")
```

## How to update the dataset

Only Python 3 is required (no extra packages).

```
python coletar_dados.py teste       # optional: sample of ~50 games, 1 to 2 minutes
python coletar_dados.py             # full collection
python coletar_tamanhos.py teste    # optional: console catalogs + 30 Steam games
python coletar_tamanhos.py          # storage size
python montar_base.py               # builds dados/tempo-para-zerar-jogos.csv
```

The full collection makes about 15 thousand requests to Metacritic and 15 to 50 thousand to
HowLongToBeat, with 4 concurrent requests and a pause between them. It takes a few hours. It can
be interrupted: running the same command resumes where it stopped (progress is kept in
`Coleta/parcial/`). Raw data goes into the `Coleta/` folder, which is not part of the
repository.

The size collection downloads the console catalogs (about 110 MB, a few minutes) and
queries Steam one game at a time, pausing 1.5 s between requests because of the store's
rate limit: about 4,500 requests, roughly 2 hours. It can also be interrupted and resumed.
Without it, `montar_base.py` still works and leaves the two size columns empty.

## Files

| File | Contents |
|---|---|
| `coletar_dados.py` | collection from Metacritic and HowLongToBeat |
| `coletar_tamanhos.py` | storage size (console catalogs and Steam) |
| `montar_base.py` | merging of the two sources, filters and variable construction |
| `dados/tempo-para-zerar-jogos.csv` | final dataset |
| `dados/estudios_regiao.csv` | parent-company region for each studio |
| `dados/hltb_ids.csv` | already known HowLongToBeat game IDs and names, used to guide the collection |

## How the dataset is built

1. **Join key.** The two sources share no identifier, so they are joined by the
   normalized game name: accents removed, lowercase, `&` becomes `and` and
   punctuation becomes a space. The year Metacritic appends to titles with the same name, as in
   `God of War (2005)`, is removed first.
2. **HowLongToBeat filter.** Only records of type `game` are kept (DLCs, compilations,
   mods etc. are dropped), with a known release date and at least 5 main-story time
   reports.
3. **Year validation.** A pair is accepted only if the release years in the two sources
   differ by at most 1. The final match is one-to-one: for duplicates, the pair with the
   closest year is kept and, on a tie, the record with more reports (HowLongToBeat) or
   more user ratings (Metacritic).
4. **Cleaning.** Games without a user score, metascore, platform, genre or developer
   are removed, as are compilations.

In the November 2026 collection, of the 14,464 Metacritic games, 7,251 were matched and
7,094 remained in the dataset.

### Genre

Metacritic genres are grouped into `RPG`, `Acao-Aventura` (Action-Adventure), `Aventura` (Adventure), `Tiro` (Shooter),
`Plataforma` (Platformer), `Luta` (Fighting), `Estrategia` (Strategy), `Simulacao` (Simulation), `Puzzle`, `Esporte-Corrida` (Sports-Racing) and `Outros` (Other).
The full mapping is in `GRUPOS`, in `montar_base.py`; the original genre is kept in
`genero_metacritic` for anyone who wants to group them differently.

### Age rating

`K-A` is the old acronym for `E`; `AO` was merged into `M`; `RP` (pending) and missing become
`Sem classificacao` (unrated).

### Company region

Neither source provides a country. The table `dados/estudios_regiao.csv` assigns each
studio the region of its **parent company at the time of release**:

- independent studio: the studio's own country applies;
- studio within a group: the group's headquarters applies (Ubisoft Montreal is `europa`; Naughty Dog is
  `japao`, since it belongs to Sony);
- studio that changed owners: there is one row per period (column `a_partir_de`, "starting from") and the one
  matching the game's release year applies;
- minority stakes and financial shareholders do not count as owners;
- unidentified studios are `desconhecido` (unknown).

The regions are `america_do_norte` (USA and Canada), `europa` (includes Russia and Ukraine),
`japao` and `outros` (rest of Asia, Oceania, Latin America, Africa, Middle East and
Turkey). To fix a classification, edit the table and run `python montar_base.py`.

### Storage size

No single source covers every platform, so two are used:

| Source | Platforms | What it measures |
|---|---|---|
| [Redump and No-Intro](https://github.com/libretro/libretro-database) catalogs | PlayStation, PS2, PS3, PSP, PS Vita, Dreamcast, Nintendo 64, Game Boy Advance, DS, 3DS | size of the disc image, cartridge ROM or digital package (Vita and digital 3DS) |
| eShop catalog, [titledb](https://github.com/blawar/titledb) | Nintendo Switch | download size |
| Steam store API | PC | free space required in the minimum requirements, when HowLongToBeat provides the game's Steam ID |

- **Matching:** console catalogs are matched by normalized name, as in the main join.
  Among versions of the same game the US one is used (then World, Europe, others,
  Japan). Multi-disc games have their discs added up. Demos, DLC, themes, prototypes and
  re-releases (Virtual Console etc.) are left out.
- **Multiplatform games:** the size on the oldest platform, among the consoles the game
  came out on that have data, is used. Steam is only used when there is no console size.
- **Platforms without data:** PS4, PS5, Xbox One and Series, Switch 2 (no open catalog),
  Xbox 360, GameCube, Wii (the disc image has a practically fixed size) and Wii U.
  Games exclusive to them have no size unless they have a Steam ID.

## Limitations

- **Name-based join.** Games spelled differently in the two sources are not matched, and
  about half of the Metacritic games are left out for this reason or for lack of reports.
- **Average of voluntary reports.** Times come from players who chose to report them; games
  with few reports have unstable averages (`n_relatos` can be used as a weight or a filter).
- **Main version on Metacritic.** Year, developer and counts are those of the version
  Metacritic shows as the main one, which may not be the original release.
- **Region table.** Part of it was built by hand and part (367 studios, added in
  November 2026) was proposed with AI assistance and only partially verified. Corrections
  are welcome.
- **Size measures different things depending on the source.** On consoles it is the actual
  file; on DS and 3DS cartridges it is the cartridge capacity, which comes in powers of 2.
  On Steam it is the space declared by the developer, rounded, for the current version of
  the store page: games that received large updates look bigger than they were at launch.
  The order of magnitude also changes a lot between generations (megabytes on cartridges,
  tens of gigabytes on PC), so size usually enters a model on the log scale and together
  with `plataforma_tamanho`.
- **Missing sizes are not random.** They concentrate on PlayStation 4 and 5, Xbox and
  Nintendo home-console exclusives. Fitting a model only on games with a size changes the
  population being studied.
- **Partial HowLongToBeat coverage.** The collection visits the known IDs whose name matches
  some Metacritic game, plus all new IDs; an old game renamed on the site may
  not be revisited. The `--hltb-completo` option visits all of them.

## Credits

- Data comes from [Metacritic](https://www.metacritic.com) and
  [HowLongToBeat](https://howlongtobeat.com). This project is not affiliated with either,
  and use of the data is subject to each site's terms.
- The collection is based on the approach of two projects, which also served as the starting
  point for the first version of the dataset (via Kaggle):
  - [davutbayik/metacritic-backend-scraper](https://github.com/davutbayik/metacritic-backend-scraper)
    ([Kaggle data](https://www.kaggle.com/datasets/davutb/metacritic-games/data));
  - [zaireali649/howlongtobeat-scraper](https://github.com/zaireali649/howlongtobeat-scraper)
    ([Kaggle data](https://www.kaggle.com/datasets/zaireali/howlongtobeat-games-scraper-2162025)).
- Sizes: [Redump](http://redump.org) and [No-Intro](https://no-intro.org) catalogs, as
  compiled in [libretro-database](https://github.com/libretro/libretro-database);
  [titledb](https://github.com/blawar/titledb) (Switch eShop); and the
  [Steam](https://store.steampowered.com) store.
- Most of the code was written by Claude (Anthropic), based on the joining, filtering
  and classification rules defined for the project.
