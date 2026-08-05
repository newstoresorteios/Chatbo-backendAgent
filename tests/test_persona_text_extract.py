from app.services.persona_text_extract import extract_text, allowed_filename


def test_allowed_filename():
    assert allowed_filename("faq.txt")
    assert allowed_filename("guia.PDF")
    assert not allowed_filename("foto.png")


def test_extract_text_plain():
    text = extract_text("politica.md", b"# Politica\nSem inventar preco.", "text/markdown")
    assert "Politica" in text
    assert "Sem inventar preco" in text
