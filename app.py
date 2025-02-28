import os
import re
import PyPDF2
import pandas as pd
import gc
from flask import Flask, request, render_template, redirect, url_for, send_file
# import openpyxl
# from openpyxl.utils.dataframe import dataframe_to_rows

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
    try:
        with open(file_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            text = "\n".join(page.extract_text()
                             for page in reader.pages if page.extract_text())

            # Verifica se o texto foi extraído corretamente
            if not text:
                print(
                    f"Erro: Não foi possível extrair texto do arquivo {file_path}.")
                return None
            else:
                # Log dos primeiros 500 caracteres
                print(
                    f"Texto extraído do arquivo {file_path}:\n{text[:500]}...")

        # Expressões regulares para encontrar os dados
        oficio = re.search(r'Ofício Nº\s*(\d+/\d+)', text)
        referencia = re.search(r'REF\s*(\d+/\d+)', text)
        hospital = re.search(
            r'À Empresa\s*(.*?)\s*(Código de Validação|$)', text, re.DOTALL)
        medico = re.search(r'laudo médico do Dr\.\s*(.*?)\s*e análise', text)
        paciente = re.search(r'paciente:\s*(.*?)\s*Termo de Adesão', text)
        parentesco = re.search(r'Termo de Adesão Nº \d+,\s*\((.*?)\)', text)
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
                    # Pega o último valor da linha
                    valor_total = line.split()[-1]
                    break
                if line.strip():  # Verifica se a linha não está vazia
                    columns = line.split()
                    if len(columns) >= 4:  # Verifica se há colunas suficientes
                        procedimento = columns[2]

        # Captura o procedimento completo
        procedimento_match = re.search(
            r'aos procedimentos:.*?\((.*?)\)\s*(.*?)\s*\((\d+x)\)', text, re.DOTALL)
        if procedimento_match:
            procedimento = f"{procedimento_match.group(2)} ({procedimento_match.group(3)})"

        # Captura o nome do hospital
        hospital_match = re.search(r'x\)\s*,\s*no\s*(.*?)\.', text)
        if hospital_match:
            hospital = hospital_match.group(1)

        # Retorna os dados extraídos
        return {
            "numero_oficio": oficio.group(1) if oficio else "Não encontrado",
            "numero_ref": referencia.group(1) if referencia else "Não encontrado",
            "hospital": hospital.group(1) if hospital else "Não encontrado",
            "nome_medico": medico.group(1) if medico else "Não encontrado",
            "nome_paciente": paciente.group(1) if paciente else "Não encontrado",
            "termo_adesao": termo_adesao.group(1) if termo_adesao else "Não encontrado",
            "parentesco": parentesco.group(1) if parentesco else "Não encontrado",
            "procedimento": procedimento,
            "valor_total": valor_total
        }

    except Exception as e:
        print(f"Erro ao processar o arquivo {file_path}: {str(e)}")
        return {
            "numero_oficio": "Não encontrado",
            "numero_ref": "Não encontrado",
            "hospital": "Não encontrado",
            "nome_medico": "Não encontrado",
            "nome_paciente": "Não encontrado",
            "termo_adesao": "Não encontrado",
            "parentesco": "Não encontrado",
            "procedimento": "Não encontrado",
            "valor_total": "Não encontrado"
        }


def save_to_excel(data, excel_path):
    global global_df
    if global_df is None:
        global_df = pd.DataFrame(columns=[
            "MÊS", "DATA ENTRADA", "PROCESSO", "OFÍCIO", "TITULARIDADE", "PACIENTE",
            "DATA DE SAÍDA DO OFÍCIO", "CREDENCIADO", "VALOR", "HOSPITAL", "CONDIÇÃO",
            "MEDICO", "DATA DO PROCEDIMENTO", "HORA DE SAÍDA DO OFICIO", "PROCEDIMENTO"
        ])

    new_row = {
        "MÊS": "",
        "DATA ENTRADA": "",
        "PROCESSO": data["numero_ref"],
        "OFÍCIO": data["numero_oficio"],
        "TITULARIDADE": data["parentesco"],
        "PACIENTE": data["nome_paciente"],
        "DATA DE SAÍDA DO OFÍCIO": "",
        "CREDENCIADO": data["hospital"],
        "VALOR": data["valor_total"],
        "HOSPITAL": data["hospital"],
        "CONDIÇÃO": "",
        "MEDICO": data["nome_medico"],
        "DATA DO PROCEDIMENTO": "",
        "HORA DE SAÍDA DO OFICIO": "",
        "PROCEDIMENTO": data["procedimento"]
    }

    global_df = pd.concat(
        [global_df, pd.DataFrame([new_row])], ignore_index=True)
    global_df.to_excel(excel_path, index=False)
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
        if not files:
            return render_template('index.html', error_message="Nenhum arquivo selecionado.")

        global global_df  # Referencia a variável global

        # Inicializa o DataFrame global se estiver vazio
        if global_df is None:
            global_df = pd.DataFrame(columns=[
                "MÊS", "DATA ENTRADA", "PROCESSO", "OFÍCIO", "TITULARIDADE", "PACIENTE",
                "DATA DE SAÍDA DO OFÍCIO", "CREDENCIADO", "VALOR", "HOSPITAL", "CONDIÇÃO",
                "MEDICO", "DATA DO PROCEDIMENTO", "HORA DE SAÍDA DO OFICIO", "PROCEDIMENTO"
            ])

        success_count = 0  # Contador de arquivos processados com sucesso
        error_messages = []  # Lista para armazenar mensagens de erro

        for file in files:
            try:
                if file.filename == '' or not file.filename.endswith('.pdf'):
                    error_messages.append(
                        f"Formato de arquivo inválido: {file.filename}")
                    continue

                file_path = os.path.join(
                    app.config['UPLOAD_FOLDER'], file.filename)
                file.save(file_path)
                extracted_data = extract_data_from_pdf(file_path)

                if not extracted_data:
                    error_messages.append(
                        f"Erro ao extrair dados do arquivo {file.filename}.")
                    continue

                # Adiciona os dados extraídos ao DataFrame global
                save_to_excel(extracted_data, os.path.join(
                    app.config['EXCEL_FOLDER'], 'dados.xlsx'))
                success_count += 1  # Incrementa o contador de sucessos

            except Exception as e:
                error_messages.append(
                    f"Erro ao processar o arquivo {file.filename}: {str(e)}")
                continue

        # Salva o DataFrame global no Excel após processar todos os PDFs
        excel_path = os.path.join(app.config['EXCEL_FOLDER'], 'dados.xlsx')
        global_df.to_excel(excel_path, index=False)

        # Mensagem de sucesso ou erro
        if success_count > 0:
            success_message = f"{success_count} arquivo(s) processado(s) com sucesso!"
            if error_messages:
                success_message += " Erros: " + ", ".join(error_messages)
            return render_template('index.html', success_message=success_message)
        else:
            return render_template('index.html', error_message="Nenhum arquivo foi processado com sucesso. Erros: " + ", ".join(error_messages))

    except Exception as e:
        return render_template('index.html', error_message=f"Erro ao processar os arquivos: {str(e)}")


@app.route('/download_excel')
def download_excel():
    excel_path = os.path.join(app.config['EXCEL_FOLDER'], 'dados.xlsx')
    if not os.path.exists(excel_path):
        return render_template('index.html', files=os.listdir(app.config['UPLOAD_FOLDER']), error="Nenhuma tabela Excel foi criada ainda. Envie PDFs para gerar a tabela.")
    return send_file(excel_path, as_attachment=True)


@app.route('/create_excel', methods=['POST'])
def create_excel():
    global global_df

    excel_path = os.path.join(app.config['EXCEL_FOLDER'], 'dados.xlsx')
    if os.path.exists(excel_path):
        try:
            os.remove(excel_path)
        except PermissionError:
            return render_template('index.html', files=os.listdir(app.config['UPLOAD_FOLDER']), error="O arquivo Excel está em uso. Feche o arquivo e tente novamente.")

    # Reseta o DataFrame global
    global_df = None
    return redirect(url_for('index'))


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
