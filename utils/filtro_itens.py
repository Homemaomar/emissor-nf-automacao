def interpretar_itens(texto: str):

    resultado = set()

    if not texto:
        return None

    partes = texto.split(",")

    for parte in partes:

        parte = parte.strip()

        # INTERVALO (1-5)
        if "-" in parte:
            inicio, fim = parte.split("-")

            try:
                inicio = float(inicio)
                fim = float(fim)

                atual = inicio
                while atual <= fim:
                    if atual.is_integer():
                        resultado.add(str(int(atual)))
                    else:
                        resultado.add(str(atual))
                    atual += 1

            except:
                continue

        else:
            resultado.add(parte)

    return list(resultado)