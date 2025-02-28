import os
import re
import PyPDF2
import pandas as pd
import gc
from flask import Flask, request, render_template, redirect, url_for, send_file
import openpyxl
from openpyxl.utils.dataframe import dataframe_to_rows


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['EXCEL_FOLDER'] = 'excel_files'

# Garante que as pastas de uploads e Excel existem
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['EXCEL_FOLDER']):
    os.makedirs(app.config['EXCEL_FOLDER'])

# Variável global para armazenar o DataFrame da tabela Excel
global_df = None  # Inicializada no escopo global


def extract_data_from_pdf(file_path):
    with open(file_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        text = "\n".join(page.extract_text()
                         for page in reader.pages if page.extract_text())

    # Expressões regulares para encontrar os dados
    oficio = re.search(r'Ofício Nº\s*(\d+)', text)
    referencia = re.search(r'REF\s*(\d+)', text)
    hospital = re.search(r'À Empresa\s*(.*?)\s*(Código de Validação|$)', text)
    medico = re.search(r'laudo médico do Dr\.\s*(.*?)\s*e análise', text)
    paciente = re.search(r'paciente:\s*(.*?)\s*Termo de Adesão', text)

    # Ajuste na expressão regular para capturar o parentesco
    parentesco = re.search(r'Termo de Adesão Nº \d+,\s*\((.*?)\)', text)
    parentesco = parentesco.group(1) if parentesco else "Não encontrado"

    termo_adesao = re.search(r'Termo de Adesão Nº\s*(\d+)', text)

    # Procedimento e valor total: processamento da tabela
    procedimento = "Não encontrado"
    valor_total = "Não encontrado"

    # Encontrar tabelas e capturar os valores necessários
    table_start = text.find("ITEM")
    if table_start != -1:
        table_text = text[table_start:]
        lines = table_text.split('\n')
        for line in lines:
            if "ESPECIFICAÇÃO" in line:
                continue  # Pular o cabeçalho da tabela
            if "TOTAL" in line:
                valor_total = line.split()[-1]  # Pega o último valor da linha
                break
            if line.strip():  # Verifica se a linha não está vazia
                columns = line.split()
                if len(columns) >= 4:  # Verifica se há colunas suficientes
                    # Assume que o procedimento está na terceira coluna
                    procedimento = columns[2]

    return {
        "numero_oficio": oficio.group(1) if oficio else "Não encontrado",
        "numero_ref": referencia.group(1) if referencia else "Não encontrado",
        "hospital": hospital.group(1).strip() if hospital else "Não encontrado",
        "nome_medico": medico.group(1).strip() if medico else "Não encontrado",
        "nome_paciente": paciente.group(1).strip() if paciente else "Não encontrado",
        "termo_adesao": termo_adesao.group(1) if termo_adesao else "Não encontrado",
        "parentesco": parentesco,
        "procedimento": procedimento,
        "valor_total": valor_total
    }


def save_to_excel(data, excel_path):
    global global_df  # Referencia a variável global

    # Se o DataFrame global não estiver carregado, cria um novo
    if global_df is None:
        global_df = pd.DataFrame(columns=[
            "Ofício Nº", "Referência", "Hospital", "Nome do Médico",
            "Nome do Paciente", "Termo de Adesão Nº", "Parentesco",
            "Procedimento", "Valor Total"
        ])

    # Cria um dicionário com os dados mapeados para as colunas corretas
    new_row = {
        "Ofício Nº": data["numero_oficio"],
        "Referência": data["numero_ref"],
        "Hospital": data["hospital"],
        "Nome do Médico": data["nome_medico"],
        "Nome do Paciente": data["nome_paciente"],
        "Termo de Adesão Nº": data["termo_adesao"],
        "Parentesco": data["parentesco"],
        "Procedimento": data["procedimento"],
        "Valor Total": data["valor_total"]
    }

    # Adiciona os novos dados ao DataFrame
    global_df = pd.concat(
        [global_df, pd.DataFrame([new_row])], ignore_index=True)

    # Salva o DataFrame no arquivo Excel
    global_df.to_excel(excel_path, index=False)

    # Libera recursos e fecha o arquivo

    gc.collect()


@app.route('/')
def index():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('index.html', files=files)


@app.route('/result')
def result():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('result.html', files=files)


@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return render_template('index.html', error_message="Nenhum arquivo selecionado.")
        files = request.files.getlist('file')
        for file in files:
            if file.filename == '' or not file.filename.endswith('.pdf'):
                return render_template('index.html', error_message="Formato de arquivo inválido.")
            file_path = os.path.join(
                app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            extracted_data = extract_data_from_pdf(file_path)
            excel_path = os.path.join(app.config['EXCEL_FOLDER'], 'dados.xlsx')
            save_to_excel(extracted_data, excel_path)
        return render_template('index.html', success_message="Arquivo extraído com sucesso!")

    except Exception as e:
        return render_template('index.html', error_message="Ocorreu um erro ao enviar o arquivo.")


@app.route('/upload_excel', methods=['POST'])
def upload_excel():
    global global_df  # Referencia a variável global

    if 'excel_file' not in request.files:
        return redirect(request.url)
    excel_file = request.files['excel_file']
    if excel_file.filename == '' or not excel_file.filename.endswith('.xlsx'):
        return redirect(request.url)

    # Carrega o arquivo Excel enviado pelo usuário
    excel_path = os.path.join(app.config['EXCEL_FOLDER'], 'dados.xlsx')
    excel_file.save(excel_path)
    global_df = pd.read_excel(excel_path)

    return redirect(url_for('index'))


@app.route('/download_excel')
def download_excel():
    excel_path = os.path.join(app.config['EXCEL_FOLDER'], 'dados.xlsx')
    if not os.path.exists(excel_path):
        return render_template('index.html', files=os.listdir(app.config['UPLOAD_FOLDER']), error="Nenhuma tabela Excel foi criada ainda. Envie PDFs para gerar a tabela.")
    return send_file(excel_path, as_attachment=True)


@app.route('/create_excel', methods=['POST'])
def create_excel():
    global global_df  # Referencia a variável global

    excel_path = os.path.join(app.config['EXCEL_FOLDER'], 'dados.xlsx')
    if os.path.exists(excel_path):
        try:
            os.remove(excel_path)
        except PermissionError:
            return render_template('index.html', files=os.listdir(app.config['UPLOAD_FOLDER']), error="O arquivo Excel está em uso. Feche o arquivo e tente novamente.")

    # Reseta o DataFrame global
    global_df = None
    return redirect(url_for('index'))


@app.route('/delete_all_pdfs')
def delete_all_pdfs():
    # Diretório onde os PDFs estão armazenados
    upload_folder = app.config['UPLOAD_FOLDER']

    # Verifica se o diretório existe
    if os.path.exists(upload_folder):
        # Remove todos os arquivos no diretório
        for file_name in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, file_name)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Erro ao excluir {file_path}: {e}")

    return redirect(url_for('result'))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
