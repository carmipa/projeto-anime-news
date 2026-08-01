"""
Especificação executável do filtro de notícias.

Este ficheiro substitui `verify_filters_manual.py`, que continha exatamente
estes casos mas rodava só à mão — e estava 7/9 há meses sem ninguém ver:
"New Demon Slayer Season Announced" era BLOQUEADO (a lista de termos estritos
não conhecia a franquia) e "Figure One Piece Nami" era APROVADO (não havia
nenhum termo de merch na blacklist, apesar do readme prometer o contrário).

Teste que não corre na suíte não é teste, é documentação que envelhece.
"""
import pytest

from core.filters import match_intel

TODOS = {"123": {"filters": ["todos"], "channel_id": 1}}
CATEGORIAS = {"123": {"filters": ["anime", "news", "games", "filmes"], "channel_id": 1}}

# Canal REAL de cada ID (confirmado pelo título do próprio feed).
# O ficheiro antigo usava UC14Yc2Q... a chamar-lhe "Netflix Japan"; é a TOHO
# animation. Era esse engano, replicado no código, que punha estúdios de anime
# na cesta das fontes mistas.
NETFLIX_JP = "https://www.youtube.com/feeds/videos.xml?channel_id=UCv2ejD5B1xOYtGB2cf80B8g"
TOHO = "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q"
CRUNCHYROLL = "https://www.youtube.com/feeds/videos.xml?channel_id=UC6pGDc4bFGD1_36IKv3FnYg"
ANN = "https://www.animenewsnetwork.com/news/rss.xml"


@pytest.mark.parametrize("titulo,resumo,deve_passar,motivo", [
    # --- anime: tem de passar ---
    ("New Demon Slayer Season Announced", "The infinite castle arc begins.", True, "franquia é termo estrito"),
    ("One Piece Episode 1000 Trailer", "Watch the new PV.", True, "one piece + pv"),
    ("Studio MAPPA releases new visual", "Chainsaw man movie visual.", True, "estúdio âncora"),
    ("One Piece Episode 1100 Release Date", "New episode coming soon.", True, "one piece"),
    ("Elden Ring Anime announced", "FromSoftware game gets an adaptation.", True, "anime baseado em jogo ainda é anime"),

    # --- games: não é notícia de anime ---
    ("Dragon Ball Sparking Zero Gameplay Reveal", "Watch 10 mins of ps5 footage.", False, "gameplay"),

    # --- merch e roupas ---
    ("Uniqlo x Naruto T-Shirt Collection", "New apparel available now.", False, "t-shirt"),
    ("New Bandai Namco Figure", "Detailed statue of Goku.", False, "figure no título"),
    ("Figure One Piece Nami", "New figure availability.", False, "figure no título"),
])
def test_spec_do_filtro(titulo, resumo, deve_passar, motivo):
    assert match_intel("123", titulo, resumo, TODOS) is deve_passar, motivo


def test_merch_no_titulo_bloqueia_mas_no_resumo_nao():
    """
    Boilerplate de loja na descrição não pode matar episódio legítimo.
    Medido em produção: com "merchandise" a valer no resumo, 10 episódios da
    Muse Asia (One-Punch Man, Iruma-kun, Rilakkuma...) eram bloqueados pelo
    rodapé "check out our merch store" da descrição.
    """
    assert match_intel("123", "Nendoroid de Frieren revelado", "", TODOS) is False
    assert match_intel(
        "123",
        "One-Punch Man - Episode 25 [English Sub]",
        "Watch on Muse Asia. Check out our merchandise store for figures!",
        TODOS,
    ) is True


def test_termo_japones_casa_no_meio_da_frase():
    """
    Kana e kanji contam como \\w, logo `\\bアニメ\\b` nunca casa em japonês, que
    não separa palavras por espaço. Se este teste falhar, o bot voltou a ficar
    cego para todo o feed dos estúdios japoneses.
    """
    assert match_intel("123", "TVアニメ『対ありでした。』第4話", "", CATEGORIAS) is True
    assert match_intel("123", "劇場版の公開日が決定", "", CATEGORIAS) is True


def test_blacklist_japonesa_bloqueia():
    """A blacklist de esportes JP existia mas nunca bloqueou nada pelo mesmo motivo."""
    assert match_intel("123", "侍ジャパンの野球中継、アニメ特番も", "", TODOS) is False


def test_fonte_mista_exige_termo_no_titulo():
    """
    Fonte mista (streaming genérico) só passa com o termo de anime no TÍTULO;
    fonte confiável pode ter o termo no resumo.
    """
    titulo, resumo = "Trailer da nova série", "A adaptação em anime estreia em outubro"
    assert match_intel("123", titulo, resumo, TODOS, source=NETFLIX_JP) is False
    assert match_intel("123", titulo, resumo, TODOS, source=ANN) is True


@pytest.mark.parametrize("fonte,nome", [
    (TOHO, "TOHO animation"),
    (CRUNCHYROLL, "Crunchyroll"),
    ("https://www.youtube.com/feeds/videos.xml?channel_id=UCivtAzCENYI1jb6Clxydvdw", "WIT STUDIO"),
    ("https://www.youtube.com/feeds/videos.xml?channel_id=UCY5fcqgSrQItPAX_Z5Frmwg", "KADOKAWAanime"),
])
def test_estudios_de_anime_nao_sao_fonte_mista(fonte, nome):
    """
    Regressão: estes quatro estavam marcados como fontes mistas por engano de
    identificação do channel_id, e isso custava 13 notícias por dia.
    """
    from core.filters import _is_untrusted_source
    assert _is_untrusted_source(fonte) is False, f"{nome} não pode ser fonte mista"


@pytest.mark.parametrize("fonte,nome", [
    ("https://www.youtube.com/feeds/videos.xml?channel_id=UCKy1dAqELo0zrOtPkf0eTMw", "IGN"),
    ("https://www.youtube.com/feeds/videos.xml?channel_id=UCJx5KP-pCUmL9eZUv-mIcNw", "GameTrailers"),
    (NETFLIX_JP, "Netflix Japan"),
])
def test_fontes_mistas_continuam_marcadas(fonte, nome):
    """
    O contrário do teste acima: os hints antigos ("ign", "gametrailers") eram
    letra morta porque a URL desses feeds só tem o channel_id.
    """
    from core.filters import _is_untrusted_source
    assert _is_untrusted_source(fonte) is True, f"{nome} tem de ser fonte mista"
