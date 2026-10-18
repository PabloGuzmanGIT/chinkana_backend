"""Crea las tablas y, si la BD está vacía, el local, el primer admin y una carta de ejemplo."""
from decimal import Decimal

from sqlalchemy import select

from config import ADMIN_PASS, ADMIN_USER, LOCAL_ID
from db import Base, SessionLocal, engine
from models import Categoria, Local, Producto, Staff
from security import hash_clave

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


def iniciar() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(Local, LOCAL_ID):
            db.add(Local(id=LOCAL_ID, nombre="Chinkana Ayacucho"))
            db.flush()

        if not db.scalar(select(Staff).where(Staff.local_id == LOCAL_ID)):
            db.add(Staff(local_id=LOCAL_ID, usuario=ADMIN_USER, nombre="Administrador",
                         clave_hash=hash_clave(ADMIN_PASS), rol="admin"))
            print(f"Admin creado: usuario '{ADMIN_USER}'. Cambia la clave en .env antes de producción.")

        if not db.scalar(select(Categoria).where(Categoria.local_id == LOCAL_ID)):
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
