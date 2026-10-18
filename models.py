"""Tablas. Todas llevan local_id para poder atender varios locales con la misma app."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def ahora():
    return datetime.now()


class Local(Base):
    __tablename__ = "locales"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    creado: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (UniqueConstraint("local_id", "usuario"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    usuario: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(80))
    clave_hash: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(20), default="staff")   # admin | staff
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (UniqueConstraint("local_id", "telefono"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    telefono: Mapped[str | None] = mapped_column(String(15))     # 51 + 9 dígitos
    nombre: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160))
    google_sub: Mapped[str | None] = mapped_column(String(64))
    acepto_terminos: Mapped[datetime | None] = mapped_column(DateTime)
    visitas: Mapped[int] = mapped_column(Integer, default=0)
    creado: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    ultima_visita: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Dispositivo(Base):
    __tablename__ = "dispositivos"
    __table_args__ = (UniqueConstraint("local_id", "mac"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"))
    mac: Mapped[str] = mapped_column(String(17))
    primera_vez: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    ultima_vez: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Sesion(Base):
    """La llenará el colector (lee /ip/hotspot/active cada minuto). Fase MikroTik."""
    __tablename__ = "sesiones"
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    mac: Mapped[str] = mapped_column(String(17), index=True)
    usuario: Mapped[str | None] = mapped_column(String(60))
    ip: Mapped[str | None] = mapped_column(String(15))
    inicio: Mapped[datetime] = mapped_column(DateTime)
    fin: Mapped[datetime | None] = mapped_column(DateTime)
    bytes_in: Mapped[int] = mapped_column(Integer, default=0)
    bytes_out: Mapped[int] = mapped_column(Integer, default=0)


class Ticket(Base):
    """Códigos de 3 h / 8 h. Se crean también como usuarios del hotspot. Fase MikroTik."""
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("local_id", "codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(20))
    horas: Mapped[int] = mapped_column(Integer)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    usado: Mapped[datetime | None] = mapped_column(DateTime)


class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(60))
    emoji: Mapped[str] = mapped_column(String(8), default="")
    orden: Mapped[int] = mapped_column(Integer, default=0)


class Producto(Base):
    __tablename__ = "productos"
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    nombre: Mapped[str] = mapped_column(String(80))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    precio: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    emoji: Mapped[str] = mapped_column(String(8), default="")
    foto: Mapped[str | None] = mapped_column(String(120))            # archivo en media/productos/
    propio: Mapped[bool] = mapped_column(Boolean, default=False)     # elaboración propia (café, chocolate)
    temperatura: Mapped[str] = mapped_column(String(10), default="ambas")   # caliente | fria | ambas
    destacado: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class Flyer(Base):
    """Afiche promocional que rota en el carrusel del portal."""
    __tablename__ = "flyers"
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(100), default="")
    imagen: Mapped[str] = mapped_column(String(120))                # archivo en media/flyers/
    clima: Mapped[str] = mapped_column(String(10), default="siempre")   # siempre | frio | calor
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id", ondelete="SET NULL"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class Promo(Base):
    """Promo manual del día: si hay una activa para hoy, reemplaza a la del clima."""
    __tablename__ = "promos"
    id: Mapped[int] = mapped_column(primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    titulo: Mapped[str] = mapped_column(String(100))
    texto: Mapped[str] = mapped_column(Text, default="")
    producto_ids: Mapped[list] = mapped_column(JSON, default=list)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class Ajuste(Base):
    __tablename__ = "ajustes"
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), primary_key=True)
    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    valor: Mapped[str] = mapped_column(Text, default="")


class ClimaCache(Base):
    __tablename__ = "clima_cache"
    local_id: Mapped[int] = mapped_column(ForeignKey("locales.id"), primary_key=True)
    temp: Mapped[float] = mapped_column(Float)
    codigo: Mapped[int] = mapped_column(Integer)
    actualizado: Mapped[datetime] = mapped_column(DateTime)
