"""Crea las tablas y, si la BD está vacía, el local, el primer admin y una carta de ejemplo."""
from decimal import Decimal

from sqlalchemy import inspect, select, text

from config import ADMIN_PASS, ADMIN_PASS_GENERADA, ADMIN_USER, LOCAL_ID
from db import Base, SessionLocal, engine
from models import Categoria, Local, Producto, Staff
from security import hash_clave
from services import catalogo

# (categoría, emoji, [(nombre, descripción, precio, emoji, propio, temperatura, destacado)])
CARTA_EJEMPLO = [
    ("Cafés de la casa", "☕", [
        ("Espresso", "Corto e intenso, de nuestro tueste.", 6, "☕", True, "caliente", False),
        ("Americano", "Espresso alargado con agua caliente.", 7, "☕", True, "caliente", False),
        ("Capuchino", "Espresso, leche vaporizada y espuma.", 10, "☕", True, "caliente", True),
        ("Latte", "Suave, con mucha leche.", 10, "🥛", True, "caliente", False),
        ("Café helado", "Nuestro café en frío con hielo.", 11, "🧊", True, "fria", True),
    ]),
    ("Chocolates", "🍫", [
        ("Chocolate caliente de la casa", "Hecho con nuestro chocolate, espeso y aromático.", 10, "🍫", True, "caliente", True),
        ("Chocolate con canela y clavo", "Receta tradicional ayacuchana.", 11, "🍫", True, "caliente", False),
        ("Chocolatada fría", "Nuestro chocolate batido con leche y hielo.", 11, "🥤", True, "fria", True),
        ("Tableta de chocolate 70 %", "Para llevar. Elaborada por nosotros.", 15, "🍫", True, "ambas", False),
    ]),
    ("Bebidas calientes", "🫖", [
        ("Infusión de muña", "Hierba andina, ideal para el frío.", 5, "🌿", False, "caliente", False),
        ("Ponche de ajonjolí", "Caliente, como en casa.", 8, "🥣", False, "caliente", True),
    ]),
    ("Frappés y bebidas frías", "🧊", [
        ("Frappé de café", "Con nuestro café, hielo y crema.", 13, "🥤", True, "fria", True),
        ("Frappé de chocolate", "Con nuestro chocolate.", 13, "🥤", True, "fria", False),
        ("Ponche de ajonjolí helado", "La versión fría del clásico.", 9, "🥛", False, "fria", True),
        ("Limonada", "Recién exprimida.", 7, "🍋", False, "fria", False),
    ]),
    ("Bubble tea", "🧋", [
        ("Bubble tea de maracuyá", "Con perlas de tapioca.", 14, "🧋", False, "fria", True),
        ("Bubble tea de taro", "Cremoso, con perlas de tapioca.", 14, "🧋", False, "fria", False),
        ("Bubble tea de chocolate", "Con nuestro chocolate y perlas.", 14, "🧋", True, "fria", False),
    ]),
    ("Postres", "🍰", [
        ("Brownie de la casa", "Con nuestro chocolate.", 8, "🍫", True, "ambas", False),
        ("Torta de chocolate", "Porción.", 9, "🍰", True, "ambas", False),
        ("Alfajor", "Relleno de manjar.", 4, "🍪", False, "ambas", False),
    ]),
]


def _columnas_nuevas() -> None:
    """create_all no agrega columnas a tablas que ya existen: las de la integración con admintienda van aquí."""
    existentes = {c["name"] for c in inspect(engine).get_columns("productos")}
    verdadero = "1" if engine.dialect.name == "sqlite" else "true"
    nuevas = {"externo_id": "VARCHAR(36)", "disponible": f"BOOLEAN NOT NULL DEFAULT {verdadero}", "foto_origen": "VARCHAR(300)"}
    with engine.begin() as con:
        for col, tipo in nuevas.items():
            if col not in existentes:
                con.execute(text(f"ALTER TABLE productos ADD COLUMN {col} {tipo}"))


def iniciar() -> None:
    Base.metadata.create_all(engine)
    _columnas_nuevas()
    with SessionLocal() as db:
        if not db.get(Local, LOCAL_ID):
            db.add(Local(id=LOCAL_ID, nombre="Chinkana Ayacucho"))
            db.flush()

        if not db.scalar(select(Staff).where(Staff.local_id == LOCAL_ID)):
            db.add(Staff(local_id=LOCAL_ID, usuario=ADMIN_USER, nombre="Administrador",
                         clave_hash=hash_clave(ADMIN_PASS), rol="admin"))
            if ADMIN_PASS_GENERADA:
                print(f"Admin creado: usuario '{ADMIN_USER}', clave '{ADMIN_PASS}' (generada: no había ADMIN_PASS).")
            else:
                print(f"Admin creado: usuario '{ADMIN_USER}' con la clave de ADMIN_PASS.")

        # Con admintienda la carta llega sola al sincronizar; el ejemplo es solo para probar sin POS.
        if not catalogo.configurado() and not db.scalar(select(Categoria).where(Categoria.local_id == LOCAL_ID)):
            for i, (cat, emoji, productos) in enumerate(CARTA_EJEMPLO):
                c = Categoria(local_id=LOCAL_ID, nombre=cat, emoji=emoji, orden=i)
                db.add(c)
                db.flush()
                for j, (nombre, desc, precio, em, propio, temp, dest) in enumerate(productos):
                    db.add(Producto(local_id=LOCAL_ID, categoria_id=c.id, nombre=nombre, descripcion=desc,
                                    precio=Decimal(precio), emoji=em, propio=propio, temperatura=temp,
                                    destacado=dest, orden=j))
            print("Carta de ejemplo cargada (precios de ejemplo).")
        db.commit()


if __name__ == "__main__":
    iniciar()
