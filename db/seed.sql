-- ============================================================
-- seed.sql — Catálogo inicial de la librería
-- Se ejecuta solo UNA vez, la primera vez que se levanta la base
-- (docker-entrypoint-initdb.d). Para re-ejecutarlo:
--   docker compose down -v   &&   docker compose up -d
--
-- REQUIERE que db/schema.sql haya creado estas tablas (asi las
-- llama el resto del proyecto, respetá estos nombres):
--
--   categorias(id SERIAL PRIMARY KEY, nombre TEXT UNIQUE NOT NULL)
--
--   articulos(
--       codigo      TEXT PRIMARY KEY,          -- ej: 'CUA-001'
--       nombre      TEXT NOT NULL,
--       categoria_id INTEGER NOT NULL REFERENCES categorias(id),
--       marca       TEXT,
--       unidad      TEXT,                      -- 'unidad', 'caja', 'resma'...
--       precio      NUMERIC(10,2) NOT NULL,
--       stock       INTEGER NOT NULL DEFAULT 0,
--       activo      BOOLEAN NOT NULL DEFAULT true
--   )
--
-- Tip: hay artículos con stock 0 (CUA-007, GEO-007) a propósito,
-- para probar que el agente avisa y sugiere alternativas.
-- ============================================================

-- 8 categorías (con id explícito para que los articulos puedan
-- referenciarlas por número)
INSERT INTO categorias (id, nombre) VALUES
  (1, 'Cuadernos y libretas'),
  (2, 'Escritura'),
  (3, 'Marcadores y resaltadores'),
  (4, 'Papel y resmas'),
  (5, 'Arte y pintura'),
  (6, 'Geometría y escolar'),
  (7, 'Oficina y archivo'),
  (8, 'Empaque y regalos');

-- Sin esto, el próximo id generado arrancaría en 1 y chocaría
SELECT setval(pg_get_serial_sequence('categorias', 'id'), (SELECT MAX(id) FROM categorias));

-- ------------------------------------------------------------
-- Artículos (72)
-- formato: (codigo, nombre, categoria_id, marca, unidad, precio, stock)
-- Los precios son de ejemplo: el agente NUNCA los inventa, lee esto.
-- ------------------------------------------------------------
INSERT INTO articulos (codigo, nombre, categoria_id, marca, unidad, precio, stock) VALUES

-- 1) Cuadernos y libretas
('CUA-001', 'Cuaderno A4 100 hojas rayado',            1, 'Futura',       'unidad',  3200.00, 45),
('CUA-002', 'Cuaderno A4 100 hojas en blanco',         1, 'Futura',       'unidad',  3200.00, 30),
('CUA-003', 'Cuaderno A5 50 hojas rayado',             1, 'Rivadavia',    'unidad',  1900.00, 80),
('CUA-004', 'Cuaderno A5 96 hojas rayado',             1, 'Oxford',       'unidad',  2800.00, 25),
('CUA-005', 'Libreta cuadrícula A5 200 hojas',         1, 'Cuadernia',    'unidad',  4500.00, 12),
('CUA-006', 'Cuaderno contable 200 hojas rayado',      1, 'Ledesma',      'unidad',  6800.00,  8),
('CUA-007', 'Cuaderno de dibujo A4 40 hojas',          1, 'Cachet',       'unidad',  2400.00,  0),
('CUA-008', 'Agenda escolar 2026',                     1, 'Colección',    'unidad',  7500.00, 15),
('CUA-009', 'Cuaderno termoformado A4 96 hojas',       1, 'Rivadavia',    'unidad',  3400.00, 40),

-- 2) Escritura
('ESC-001', 'Birome Bic Cristal azul',                 2, 'Bic',          'unidad',   850.00, 200),
('ESC-002', 'Birome Bic Cristal negro',                2, 'Bic',          'unidad',   850.00, 180),
('ESC-003', 'Lapicera gel Pilot negra 0.7',            2, 'Pilot',        'unidad',  2100.00, 60),
('ESC-004', 'Lápiz grafito HB nº2',                    2, 'Faber-Castell','unidad',   450.00, 300),
('ESC-005', 'Lápiz grafito 2B para dibujo',            2, 'Staedtler',    'unidad',   700.00, 90),
('ESC-006', 'Set de 12 lápices de colores',            2, 'Faber-Castell','paquete', 5800.00, 35),
('ESC-007', 'Lapicera T-10 azul',                      2, 'Pilot',        'unidad',   900.00, 150),
('ESC-008', 'Estilógrafo Pilot Blue Black',            2, 'Pilot',        'unidad',  3200.00, 25),
('ESC-009', 'Minas 0.7 para lapicera gel (x10)',       2, 'Pilot',        'paquete', 1800.00, 40),

-- 3) Marcadores y resaltadores
('MAR-001', 'Resaltador amarillo pastel',              3, 'Faber-Castell','unidad',  1300.00, 70),
('MAR-002', 'Resaltador azul pastel',                  3, 'Faber-Castell','unidad',  1300.00, 65),
('MAR-003', 'Marcador permanente negro punta fina',    3, 'Pentel',       'unidad',  1900.00, 50),
('MAR-004', 'Marcador de pizarra negro',               3, 'Pelikan',      'unidad',  1600.00, 30),
('MAR-005', 'Tizas blancas para pizarra (x10)',        3, 'Pelikan',      'caja',    2200.00, 20),
('MAR-006', 'Set de 8 marcadores fiber tip',           3, 'Norma',        'set',     4800.00, 25),
('MAR-007', 'Subrayador verde Stabilo',                3, 'Stabilo',      'unidad',  1450.00, 55),
('MAR-008', 'Borrador de pizarra',                     3, 'Pelikan',      'unidad',   950.00, 40),
('MAR-009', 'Tiza lavable color (caja x12)',           3, 'Lápicería',    'caja',    2600.00, 10),

-- 4) Papel y resmas
('PAP-001', 'Resma A4 75g blanc bond',                 4, 'Bond',         'resma',   9200.00, 60),
('PAP-002', 'Resma A4 90g',                            4, 'Ledesma',      'resma',  12500.00, 35),
('PAP-003', 'Resma A3 75g',                            4, 'Bond',         'resma',  18500.00, 15),
('PAP-004', 'Papel bond color A4 (paq x100)',          4, 'Norma',        'paquete', 6500.00, 20),
('PAP-005', 'Papel fotográfico A4 glossy (x20)',       4, 'Jet',          'paquete', 8900.00, 12),
('PAP-006', 'Block de dibujo A4 20 hojas',             4, 'Cachet',       'unidad',  1700.00, 45),
('PAP-007', 'Cartulina blanca A4 (paq x10)',           4, 'Norma',        'paquete', 2400.00, 50),
('PAP-008', 'Papel couché A4 (paq x50)',               4, 'Jet',          'paquete',11200.00,  8),
('PAP-009', 'Resma reciclada A4 75g',                  4, 'EcoPrint',     'resma',   8700.00, 22),

-- 5) Arte y pintura
('ART-001', 'Temperas lavables (caja x6)',             5, 'Faber-Castell','caja',    6900.00, 30),
('ART-002', 'Acuarelas 12 colores en pastilla',        5, 'Van Gogh',     'unidad', 15800.00, 10),
('ART-003', 'Pincel redondo nº6',                      5, 'Yarara',       'unidad',  1200.00, 60),
('ART-004', 'Pincel plana nº12',                       5, 'Yarara',       'unidad',  1850.00, 40),
('ART-005', 'Lienzo 30x40 cm con bastidor',            5, 'Cachet',       'unidad',  4900.00, 18),
('ART-006', 'Cartulina negra A3 (paq x10)',            5, 'Norma',        'paquete', 3200.00, 25),
('ART-007', 'Papel obra A4 (paq x50)',                 5, 'Cachet',       'paquete', 5400.00, 20),
('ART-008', 'Set de 24 colores al óleo',               5, 'Yarara',       'set',    18900.00,  6),
('ART-009', 'Acrílico negro 250 ml',                   5, 'Acrilex',      'unidad',  4300.00, 14),

-- 6) Geometría y escolar
('GEO-001', 'Regla plástica 30 cm',                    6, 'Norma',        'unidad',   900.00, 100),
('GEO-002', 'Compás con mina',                         6, 'Maped',        'unidad',  2300.00, 45),
('GEO-003', 'Transportador 180° plástico',             6, 'Norma',        'unidad',   850.00, 80),
('GEO-004', 'Escuadra 45° + 60° (juego)',              6, 'Norma',        'juego',   1600.00, 50),
('GEO-005', 'Sacapuntas doble con depósito',           6, 'Maped',        'unidad',   750.00, 120),
('GEO-006', 'Set de geometría 5 piezas',               6, 'Helix',        'set',     7800.00, 15),
('GEO-007', 'Mini cortina de papel',                   6, 'Maped',        'unidad',  2100.00,  0),
('GEO-008', 'Portaminas 0.5 mm',                       6, 'Faber-Castell','unidad',  2900.00, 22),
('GEO-009', 'Goma de borrar blanca',                   6, 'Faber-Castell','unidad',   650.00, 140),

-- 7) Oficina y archivo
('OFI-001', 'Carpeta plastificada A4 con anillas',     7, 'Norma',        'unidad',  2600.00, 55),
('OFI-002', 'Archivador copia y seguridad A4',         7, 'Norma',        'unidad',  3800.00, 30),
('OFI-003', 'Cinta adhesiva transparente 18 mm',       7, 'Scotch',       'unidad',  1150.00, 110),
('OFI-004', 'Cinta de embalar 48 mm',                  7, 'Scotch',       'unidad',  1900.00, 40),
('OFI-005', 'Grampa tipo mariposa (caja x12)',         7, 'One',          'caja',    1500.00, 60),
('OFI-006', 'Clips niquelados nº2 (caja x100)',        7, 'One',          'caja',    1350.00, 75),
('OFI-007', 'Ganchos para papel (paq x50)',            7, 'One',          'paquete',  980.00, 90),
('OFI-008', 'Bandeja plástica para escritorio',        7, 'Norma',        'unidad',  3400.00, 12),
('OFI-009', 'Sobre manila A4 (paq x25)',               7, 'Jet',          'paquete', 2900.00, 35),

-- 8) Empaque y regalos
('BOL-001', 'Bolsa kraft con asa chica',               8, 'Kraft',        'unidad',   350.00, 400),
('BOL-002', 'Bolsa kraft con asa grande',              8, 'Kraft',        'unidad',   550.00, 300),
('BOL-003', 'Papel envoltorio rollo 10 m',             8, 'Jet',          'unidad',  2800.00, 20),
('BOL-004', 'Papel de seda (paq x12)',                 8, 'Jet',          'paquete', 1900.00, 30),
('BOL-005', 'Tarjetitas de regalo (paq x10)',          8, 'Jet',          'paquete', 1450.00, 45),
('BOL-006', 'Lazo de raso 25 m',                       8, 'Rayan',        'unidad',  2600.00, 15),
('BOL-007', 'Caja de regalo chica',                    8, 'Jet',          'unidad',  1250.00, 50),
('BOL-008', 'Caja de regalo grande',                   8, 'Jet',          'unidad',  2100.00, 35),
('BOL-009', 'Sticker de cierre (paq x100)',            8, 'Jet',          'paquete', 1600.00, 25);
