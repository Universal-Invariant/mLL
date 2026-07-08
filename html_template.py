
def get_html_template():
    """Returns the complete HTML template with embedded CSS and JavaScript."""

    js = ""
    with open("html_template.js", "r", encoding="utf-8") as file:
        js = "<script>" + file.read() + "</script>"

    css = ""
    with open("html_template.css", "r", encoding="utf-8") as file:
        css = "<style>" + file.read() + "</style>"

    with open("html_template.html", "r", encoding="utf-8") as file:
        html = file.read()
        html = html.replace("<CSSTEMPLATE />", css)
        html = html.replace("<JSTEMPLATE />", js)
        return html
