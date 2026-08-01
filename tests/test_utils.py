"""
Testes para as funções utilitárias do bot.
Estes testes NÃO importam main.py para evitar dependência do Discord token.
"""
import re


# Cópia das funções para testar (sem depender de main.py)
def clean_html(raw_html: str) -> str:
    """Remove tags HTML e entidades; normaliza espaços."""
    if not raw_html:
        return ""
    _HTML_RE = re.compile(r"<.*?>|&([a-z0-9]+|#[0-9]{1,6});", flags=re.IGNORECASE)
    _WS_RE = re.compile(r"\s+")
    txt = re.sub(_HTML_RE, " ", raw_html)
    txt = re.sub(_WS_RE, " ", txt).strip()
    return txt


def test_clean_html_basic():
    """Testa remoção de tags HTML simples."""
    assert clean_html("<p>Test</p>") == "Test"
    assert clean_html("<b>Bold</b> text") == "Bold text"


def test_clean_html_entities():
    """Testa conversão de entidades HTML."""
    result = clean_html("Hello&nbsp;World")
    assert "Hello" in result and "World" in result


def test_clean_html_whitespace():
    """Testa normalização de espaços."""
    assert clean_html("  Multiple   spaces  ") == "Multiple spaces"
    assert clean_html("\n\nNew\nlines\n\n") == "New lines"


def test_clean_html_empty():
    """Testa strings vazias."""
    assert clean_html("") == ""
    assert clean_html(None) == ""


def test_sources_json_exists():
    """Verifica que sources.json existe."""
    import os
    assert os.path.exists("sources.json"), "sources.json deve existir"


def test_sources_json_valid():
    """Verifica que sources.json é JSON válido."""
    import json
    with open("sources.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "sources.json deve ser um dicionário"
    assert "rss_feeds" in data or "youtube_feeds" in data, "Deve ter pelo menos uma categoria de feeds"


def test_sources_urls_are_valid():
    """
    Verifica que as URLs carregadas começam com http(s).

    A versão anterior só olhava para `data[key]` quando era lista — e as
    categorias do sources.json são dicionários, logo `all_urls` ficava VAZIO e
    o teste não verificava nada. Passar a usar o carregador real resolve as
    duas coisas: testa o que diz testar e acompanha mudanças de schema.
    """
    from core.sources import load_sources

    urls = load_sources()
    assert urls, "nenhuma URL carregada de sources.json"
    for url in urls:
        assert url.startswith(("http://", "https://")), f"URL inválida: {url}"


def test_readme_exists():
    """
    Verifica que o README existe, sem depender de capitalização nem do cwd.

    O ficheiro é `README.md` no git e `readme.md` no Windows (sistema de
    ficheiros insensível a maiúsculas). O teste procurava `readme.md` relativo
    ao cwd: passava no Windows e falhava em Linux — ou seja, só quebrava no
    ambiente de produção. Foi assim que a suíte passou verde aqui e vermelha
    no container 3.10.
    """
    import os

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    encontrados = [n for n in os.listdir(raiz) if n.lower() == "readme.md"]
    assert encontrados, f"nenhum README.md em {raiz}"

