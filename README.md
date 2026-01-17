Create virtual env (it will be in a directory called `.venv`)

On mac,

```bash
python3 -m venv .venv
source .venv/bin/activate
```

on windows,

```bash
python -m venv .venv
venv\Scripts\Activate.ps1
```

Install deps,

```bash
pip install -r requirements.txt
```

To update the deps,

```bash
pip freeze > requirements.txt
```

Running the server,

```bash
uvicorn app.main:app --reload
```
