"""
Capa de acceso a datos: el engine de SQLAlchemy y la fabrica de sesiones.

- engine:    el "tunel" a la base. Se crea UNA sola vez al importar el
             modulo (a nivel de modulo = singleton implicito).
- SessionLocal: fabrica que produce sesiones nuevas. Una sesion = una
             transaccion. Se usa con "with" para que siempre se cierre.
- session_scope: context manager que maneja commit/rollback por nosotros.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL

# pool_pre_ping=True manda un "SELECT 1" antes de cada uso: si la base se
# reinicio y la conexion vieja quedo muerta, SQLAlchemy la descarta y arma
# una nueva en vez de tirar un error raro.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# expire_on_commit=False: tras un commit los objetos en memoria conservan
# sus atributos (sin eso, leer algo despues del commit dispara otra query).
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Session:
    """
    Uso tipico:

        with session_scope() as s:
            fila = s.execute(...).first()

    Hace el commit si todo salio bien, o el rollback si algo exploto.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()