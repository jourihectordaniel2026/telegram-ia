-- Extensiones para la búsqueda aproximada (la vista de más abajo las usa)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- 2. Tabla de Categorias y Artículos (Catálogo de la librería)
CREATE TABLE categorias (
    id      SERIAL PRIMARY KEY,
    nombre  TEXT UNIQUE NOT NULL
);

CREATE TABLE articulos (
    codigo       TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    marca        TEXT,
    unidad       TEXT,
    precio       NUMERIC(10,2) NOT NULL,
    stock        INTEGER NOT NULL DEFAULT 0,
    activo       BOOLEAN NOT NULL DEFAULT true
);

-- 1. Tabla de Usuarios
CREATE TABLE usuarios (
    chat_id   BIGINT PRIMARY KEY,
    nombre    TEXT,
    username  TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE presupuestos (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL REFERENCES usuarios(chat_id),
    cliente_nombre TEXT,
    estado TEXT DEFAULT 'borrador' CHECK (estado IN ('borrador','confirmado','enviado','anulado')),
    descuento NUMERIC NOT NULL DEFAULT 0,
    subtotal NUMERIC NOT NULL DEFAULT 0,
    total NUMERIC NOT NULL DEFAULT 0,
    pdf_path TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. Tabla de Ítems del Presupuesto
CREATE TABLE presupuesto_items (
    id SERIAL PRIMARY KEY,
    presupuesto_id INTEGER REFERENCES presupuestos(id) ON DELETE CASCADE, -- Si borra la cabecera, borra sus ítems
    articulo_codigo TEXT REFERENCES articulos(codigo), -- Ojo: referencia a 'codigo', no a 'id'
    cantidad INTEGER CHECK (cantidad > 0),
    precio_unitario NUMERIC NOT NULL -- La copia del precio al momento de presupuestar
);

-- 5. Tabla de Mensajes
CREATE TABLE mensajes (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL REFERENCES usuarios(chat_id),
    rol TEXT CHECK (rol IN ('user','assistant')),
    contenido JSONB NOT NULL,
    creado_en TIMESTAMPTZ DEFAULT now()
);

-- 6. Tabla de Memoria de Usuario
CREATE TABLE memoria_usuario (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT REFERENCES usuarios,
    clave TEXT NOT NULL,
    valor TEXT NOT NULL,
    UNIQUE (chat_id, clave) -- eso es lo que permite que un usuario recuerde "colegio = San Martín" sin repetir la clave
);

-- 7. Vista del Catálogo (v_catalogo)

CREATE OR REPLACE FUNCTION f_normalizar(texto TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS
$$ SELECT lower(unaccent(texto)) $$;

CREATE VIEW v_catalogo AS
SELECT a.codigo,
       a.nombre,
       c.nombre AS categoria,
       a.marca,
       a.unidad,
       a.precio,
       a.stock,
       f_normalizar(a.nombre || ' ' || coalesce(a.marca, '')) AS texto_normalizado
FROM articulos a
JOIN categorias c ON c.id = a.categoria_id
WHERE a.activo;
