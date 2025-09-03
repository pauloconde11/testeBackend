from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
import pdfplumber
import tempfile
import re

app = FastAPI()

origins = [
    "https://vista-nova-navega-4075zwd38-paulocondes-projects.vercel.app",
    "http://localhost:8080"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ultima_ficha_processada = {}

def get_cell(linha, index, replace_text=""):
    if len(linha) > index and linha[index]:
        return linha[index].replace(replace_text, "").strip()
    return ""

@app.get("/")
async def root() -> Any:
    return {"message": "Bem-vindo à API de Processamento de Fichas Financeiras!"}

@app.post("/upload-ficha")
async def upload_ficha(file: UploadFile = File(...)) -> Any:
    global ultima_ficha_processada 

    if file.content_type != "application/pdf":
        return {"erro": "Arquivo enviado não é um PDF válido"}

    with tempfile.NamedTemporaryFile(dir="/tmp", delete=False, suffix=".pdf") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    dados_formatados = []
    dados_servidor = {}
    totais = {}
    tipo_atual = None

    with pdfplumber.open(tmp_path) as pdf:
        for pagina in pdf.pages:
            tabela = pagina.extract_table()
            linhas_texto = pagina.extract_text().split("\n") if pagina.extract_text() else []

            ano_referencia = None
            numero_pagina_tabela = None

            if len(linhas_texto) > 12:
                linha_12 = linhas_texto[12]
                match = re.search(r"\b(20\d{2})\b", linha_12)
                if match:
                    ano_referencia = match.group(1)

            if len(linhas_texto) > 1:
                linha_1 = linhas_texto[1]
                match_pagina = re.search(r"\b(\d{1,2})\b", linha_1)
                if match_pagina:
                    numero_pagina_tabela = int(match_pagina.group(1))

            if not tabela:
                continue

            for linha in tabela:
                if not linha or all(cell is None or str(cell).strip() == "" for cell in linha):
                    continue

                texto_linha = " ".join([str(cell) if cell else "" for cell in linha])

                if "NOME DO SERVIDOR" in texto_linha:
                    dados_servidor["NOME"] = get_cell(linha, 0, "NOME DO SERVIDOR\n")

                elif "CPF" in texto_linha:
                    dados_servidor["CPF"] = get_cell(linha, 16, "CPF\n")

                elif "MAT. SIAPE" in texto_linha:
                    dados_servidor["MATRICULA"] = get_cell(linha, 9, "MAT. SIAPE\n")

                elif "CARGO" in texto_linha:
                    dados_servidor["CARGO"] = get_cell(linha, 0, "CARGO/EMPREGO\n")

                if "TOTAL BRUTO" in texto_linha:
                    partes = texto_linha.split("TOTAL BRUTO (R$)")
                    if len(partes) > 1:
                        bruto = partes[1].split("TOTAL DESCONTOS (R$")[0].strip()
                        totais["TOTAL BRUTO"] = bruto

                elif "TOTAL DESCONTOS" in texto_linha:
                    partes = texto_linha.split("TOTAL DESCONTOS (R$)")
                    if len(partes) > 1:
                        descontos = partes[1].split("TOTAL LIQUIDO (R$")[0].strip()
                        totais["TOTAL DESCONTOS"] = descontos

                elif "TOTAL LIQUIDO" in texto_linha:
                    partes = texto_linha.split("TOTAL LIQUIDO (R$)")
                    if len(partes) > 1:
                        totais["TOTAL LIQUIDO"] = partes[1].strip()

                if linha[0] in ["RENDIMENTOS", "DESCONTOS"]:
                    tipo_atual = linha[0]

                discriminacao = get_cell(linha, 1)
                if not discriminacao:
                    continue

                valores = [
                    get_cell(linha, 7),
                    get_cell(linha, 10),
                    get_cell(linha, 12),
                    get_cell(linha, 14),
                    get_cell(linha, 17),
                    get_cell(linha, 18),
                    get_cell(linha, 20)
                ]

                registro = {
                    "TIPO": tipo_atual,
                    "DISCRIMINAÇÃO": discriminacao,
                    "ANOREFERENCIA": ano_referencia,
                    "NUMERO_PAGINA_TABELA": numero_pagina_tabela,
                    "TOTAL": valores[6]
                }

                if numero_pagina_tabela is not None and numero_pagina_tabela % 2 == 1:
                    registro.update({
                        "JAN": valores[0],
                        "FEV": valores[1],
                        "MAR": valores[2],
                        "ABR": valores[3],
                        "MAI": valores[4],
                        "JUN": valores[5]
                    })
                elif numero_pagina_tabela is not None:
                    registro.update({
                        "JUL": valores[0],
                        "AGO": valores[1],
                        "SET": valores[2],
                        "OUT": valores[3],
                        "NOV": valores[4],
                        "DEZ": valores[5]
                    })

                dados_formatados.append(registro)

    ultima_ficha_processada = {
        "dados_servidor": dados_servidor,
        "rendimentos_descontos": dados_formatados,
        "numero_pagina_tabela": numero_pagina_tabela,
        "totais": totais
    }

    return {
        "status": "ok",
        "mensagem": "Ficha processada com sucesso!",
        "anos_encontrados": list({d['ANOREFERENCIA'] for d in dados_formatados if d.get('ANOREFERENCIA')}),
        "dados": ultima_ficha_processada
    }

@app.get("/fichaFinanceiraJson")
def get_ficha_financeira_json() -> Any:
    if not ultima_ficha_processada:
        return {"mensagem": "Nenhuma ficha foi processada ainda."}
    return ultima_ficha_processada
