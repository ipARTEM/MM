# MM/mm08/tests/_utils.py
def html(resp) -> str:
    return resp.content.decode("utf-8")
