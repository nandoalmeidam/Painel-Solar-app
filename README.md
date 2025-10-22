# Painel-Solar-app

Projeto GOODWE – Passo a passo para rodar localmente
====================================================

0) Pré-requisitos
-----------------
- Python 3.11+ instalado (recomendado 3.11 ou 3.12)
- Git (opcional)
- No Windows: PowerShell

  

1) Criar / ativar o ambiente virtual (na raiz do projeto)
---------------------------------------------------------
Windows (PowerShell):
    python -m venv .venv
    .\.venv\Scripts\Activate

macOS / Linux (bash/zsh):
    python3 -m venv .venv
    source .venv/bin/activate

Dica: confirme que está no venv certo
Windows:
    where python
    where pip
macOS / Linux:
    which python
    which pip



2) Atualizar o instalador e instalar dependências
-------------------------------------------------
Sempre que ativar o venv pela 1ª vez:

    ler ANTES_DE_RODAR.txt




3) Configurar a chave do Gemini (.env)
--------------------------------------
Crie um arquivo chamado **.env** na raiz do projeto com a linha abaixo:

    GEMINI_API_KEY=coloque_sua_chave_aqui

(Dica: sem aspas. Se preferir usar aspas, também funciona.)



4) Rodar a aplicação
--------------------
Ainda com o venv ativo, na raiz do projeto:

    python -m streamlit run app.py
    (ou) 
    streamlit run app.py

O Streamlit abrirá no navegador. Para parar, use CTRL+C no terminal.



5) Estrutura esperada (simplificada)
------------------------------------
.
├─ app.py
├─ Clima.py
├─ main.py
├─ requirements.txt
├─ .env




6) Problemas comuns e soluções rápidas
--------------------------------------
• “No API_KEY or ADC found” ao perguntar algo na aba de I.A.:
    → Verifique o arquivo .env e a variável GEMINI_API_KEY (mudança também de versão).
    → Reinicie o app após ajustar.

• Pip/Streamlit aponta para outro venv antigo:
    → Feche o terminal, abra novamente, ative este .venv e rode `where python` / `where pip`.

• Erro “Microsoft Visual C++ 14.0 or greater is required” (Windows) ao instalar aiohttp/multidict:
    → Instale os Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    → Depois rode novamente `pip install -r requirements.txt`.
    → Alternativa: usar Python 3.11/3.12 e versões com wheels precompilados.

• Pastas com acentos/espaços no caminho (ex.: “Área de Trabalho”) podem causar bugs em alguns ambientes:
    → Se der problema, mova o projeto para um caminho simples (ex.: C:\dev\goodwe\).




7) Rodar novamente (resumo)
---------------------------
Windows:
    .\.venv\Scripts\Activate
    streamlit run app.py

macOS / Linux:
    source .venv/bin/activate
    streamlit run app.py
