## Quick Start

**NOTE**: The project uses Python 3.9, so need it installed first. It is recommended to use [`pyenv`](https://github.com/pyenv/pyenv) for installation.

Here is a short instruction on how to quickly set up the project for development:

1. Install [`poetry`](https://python-poetry.org/)
2. `git clone https://gitlab.com/8ergey/vtorprice.git`
3. Install requirements:

```bash
$ poetry install
$ poetry shell
```

4. Install pre-commit hooks: `$ pre-commit install`
5. Apply migrations: `$ python manage.py migrate`
6. Manually create a superuser: `$ python manage.py createsuperuser --username admin --email admin@admin.com`
7. Load test data: `$ python manage.py loaddata testdata.json`

### Use Postgres with Docker

The project used Postgres as db engine. To use postgres with docker:

1. Add `DB_ENGINE=postgres, DB_USER=postgres, DB_PASSWORD=postgres` to `.env`
2. From project root run `$ docker run --rm --volume pgdata:/var/lib/postgresql/data --name pg --env-file .env -d -p 5432:5432 postgres:12.4-alpine`



### Fix pycharm python console

In [File | Settings | Build, Execution, Deployment | Console](jetbrains://Python/settings?name=Build%2C+Execution%2C+Deployment--Console) 
Open Python console and insert following code:
```python
import sys; print('Python %s on %s' % (sys.version, sys.platform))
sys.path.extend([WORKING_DIR_AND_PYTHON_PATHS])
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "./.env"))
```

Insert this code in django console
```python
from dotenv import load_dotenv
import os, sys
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "./.env"))
sys.path.extend([WORKING_DIR_AND_PYTHON_PATHS])
import sys; print('Python %s on %s' % (sys.version, sys.platform))
import django; print('Django %s' % django.get_version())


if 'setup' in dir(django): django.setup()
import django_manage_shell; django_manage_shell.run(PROJECT_ROOT)
```