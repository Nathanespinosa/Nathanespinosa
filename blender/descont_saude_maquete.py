# -*- coding: utf-8 -*-
"""
=====================================================================
 MAQUETE ELETRÔNICA – DESCONT'SAÚDE (TÉRREO)
 Script de automação para Blender (bpy) – compatível 3.6 / 4.x / 5.x
=====================================================================

COMO USAR
  1. Abra o Blender > aba "Scripting" > New > cole este arquivo > Run Script.
  2. A viewport entra na câmera "Camera_Walkthrough_Entrada" (Material Preview).
  3. Passe o mouse sobre a viewport e pressione  Shift + `  (Shift + ~)
     para entrar em Walk Navigation:
        W A S D = andar | Mouse = olhar | Shift = correr | Alt = devagar
        Tab = liga/desliga gravidade | E / Q = subir / descer (sem gravidade)
        Clique esquerdo = confirma posição | Clique direito / Esc = cancela
  4. O script pode ser executado várias vezes: ele apaga e recria a maquete.

SISTEMA DE COORDENADAS (metros, escala 1:1)
  X = largura da loja (0 = parede esquerda interna, 7.85 = parede direita)
  Y = profundidade   (0 = vitrine/fachada, cresce para o fundo)
  Z = altura         (0 = piso acabado)

PROGRAMA (baseado na planta "março 2021" – área circulada)
  Hall 7.85 x 8.00 m (58 m²)  -> recepção, espera, vendas e circulação
  Sala 01 5.05 x 4.00 m (20 m²) -> dividida em Consultório 01 (2.44 m)
                                   e Consultório 02 (2.50 m) com drywall acústico
  San. existente (lavabo), escada para o pavimento superior e acesso à garagem.
"""

import bpy
import bmesh
from math import radians, pi, cos, sin
from mathutils import Vector, Matrix


# =====================================================================
# 0. PARÂMETROS GERAIS (edite aqui para ajustar o layout)
# =====================================================================
NOME_RAIZ = "DescontSaude_Maquete"
REMOVER_OBJETOS_PADRAO = True       # remove Cube / Light / Camera da cena nova

PE_DIREITO = 3.80                   # altura do forro (bandeira 1.45 + portas 2.30)
TOPO_LAJE = 3.96                    # nível do pavimento superior (22 x 0.18)
LARG_HALL = 7.85                    # largura interna (cota 7.85 da planta)
PROF_HALL = 8.00                    # profundidade do hall (4.95 + 3.05)
E_EXT = 0.20                        # espessura das paredes externas
E_INT = 0.10                        # espessura das paredes internas
E_DIV = 0.11                        # divisória entre consultórios (cota 0.11)

# Sala 01 -> Consultórios (cotas 0.10 | 2.44 | 0.11 | 2.50 | 0.10)
SALA_X0, SALA_X1 = 1.30, 6.35
SALA_Y0, SALA_Y1 = PROF_HALL, PROF_HALL + 4.00
DIV_X0 = SALA_X0 + 2.44             # 3.74
DIV_X1 = DIV_X0 + E_DIV             # 3.85

# Escada em "L" (Previsão de escada – 22 degraus)
ESC_Y0 = 1.65                       # início do 1º degrau
ESC_LARG = 1.20                     # largura do lance (cota 1.20)
ESPELHO = 0.18                      # altura do degrau
PISO_DEG = 0.28                     # profundidade do degrau
N_LANCE1 = 11                       # degraus 1..11 (o 12 é o patamar)
N_LANCE2 = 10                       # degraus 13..22
PAT_Y0 = ESC_Y0 + N_LANCE1 * PISO_DEG          # 4.73
PAT_Y1 = PAT_Y0 + ESC_LARG                     # 5.93
PAT_Z = (N_LANCE1 + 1) * ESPELHO               # 2.16
L2_X0 = ESC_LARG                               # 1.20
L2_X1 = L2_X0 + N_LANCE2 * PISO_DEG            # 4.00

# Lavabo existente (San. existente) – canto direito do hall
LAV_X0, LAV_X1 = 6.25, LARG_HALL
LAV_Y0, LAV_Y1 = 5.00, 7.10

ALTURA_BARRADO = 1.10               # barrado cinza nas paredes (como nas fotos)

# Cores institucionais (extraídas do logotipo / fachada)
COR = {
    "azul_marinho": "#0B3F86",
    "azul_ciano":   "#22A8E6",
    "turquesa":     "#16BFB0",
    "verde_lima":   "#8CC63F",
    "grafite":      "#1F2B28",
    "branco_gelo":  "#F2F1EC",
    "cinza_barrado": "#A9B4BC",
}

M = {}   # dicionário global de materiais


# =====================================================================
# 1. UTILITÁRIOS (cores, cena, coleções e geometria)
# =====================================================================
def lin(hexcor, a=1.0):
    """Converte cor HEX (sRGB) para RGBA linear usado pelos nodes."""
    h = hexcor.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return (c[0], c[1], c[2], a)


def limpar_cena():
    """Remove a maquete anterior (permite rodar o script várias vezes)."""
    raiz = bpy.data.collections.get(NOME_RAIZ)
    if raiz:
        colecoes = list(raiz.children_recursive) + [raiz]
        for col in colecoes:
            for ob in list(col.objects):
                bpy.data.objects.remove(ob, do_unlink=True)
        for col in colecoes:
            bpy.data.collections.remove(col)
    if REMOVER_OBJETOS_PADRAO:
        for nome in ("Cube", "Light", "Camera"):
            ob = bpy.data.objects.get(nome)
            if ob:
                bpy.data.objects.remove(ob, do_unlink=True)
    # Dados órfãos (malhas, textos, luzes e câmeras sem uso)
    for bloco in (bpy.data.meshes, bpy.data.curves, bpy.data.lights, bpy.data.cameras):
        for d in list(bloco):
            if d.users == 0:
                bloco.remove(d)


def nova_colecao(nome, pai):
    col = bpy.data.collections.new(nome)
    pai.children.link(col)
    return col


# ---- "Partes" de geometria (montadas numa única malha por objeto) ----
ROT_EIXO = {
    "Z": Matrix.Identity(4),
    "X": Matrix.Rotation(pi / 2, 4, "Y"),
    "Y": Matrix.Rotation(pi / 2, 4, "X"),
}


def B(centro, tamanho, mat):
    """Caixa por centro e tamanho (coordenadas locais)."""
    return ("box", centro, tamanho, mat)


def BX(minimo, maximo, mat):
    """Caixa por canto mínimo e máximo (x, y, z)."""
    c = tuple((a + b) / 2 for a, b in zip(minimo, maximo))
    s = tuple(abs(b - a) for a, b in zip(minimo, maximo))
    return ("box", c, s, mat)


def CY(centro, raio, altura, mat, eixo="Z"):
    """Cilindro (eixo Z, X ou Y)."""
    return ("cyl", centro, (raio, altura), mat, eixo)


def SP(centro, raio, mat):
    """Esfera."""
    return ("sph", centro, (raio,), mat)


def malha(nome, partes, col, loc=(0, 0, 0), rot_z=0.0):
    """Cria UM objeto a partir de várias partes (caixas/cilindros/esferas),
    cada uma com seu material. Partes em coordenadas locais do objeto."""
    me = bpy.data.meshes.new(nome)
    bm = bmesh.new()
    mats = []
    for p in partes:
        tipo, centro, dims, mat = p[0], Vector(p[1]), p[2], p[3]
        if mat not in mats:
            mats.append(mat)
        idx = mats.index(mat)
        if tipo == "box":
            verts = bmesh.ops.create_cube(bm, size=1.0)["verts"]
            bmesh.ops.scale(bm, vec=Vector(dims), verts=verts)
            bmesh.ops.translate(bm, vec=centro, verts=verts)
            liso = False
        elif tipo == "cyl":
            mtx = Matrix.Translation(centro) @ ROT_EIXO[p[4]]
            verts = bmesh.ops.create_cone(
                bm, cap_ends=True, cap_tris=False, segments=24,
                radius1=dims[0], radius2=dims[0], depth=dims[1], matrix=mtx)["verts"]
            liso = True
        else:  # esfera
            verts = bmesh.ops.create_uvsphere(
                bm, u_segments=24, v_segments=12, radius=dims[0],
                matrix=Matrix.Translation(centro))["verts"]
            liso = True
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index = idx
            f.smooth = liso and len(f.verts) <= 4
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(nome, me)
    ob.location = loc
    ob.rotation_euler = (0.0, 0.0, rot_z)
    col.objects.link(ob)
    return ob


def objeto_mundo(nome, partes, col):
    """Recebe partes em coordenadas do MUNDO e centraliza a origem do objeto
    no centro do conjunto (origem organizada para mover/rotacionar)."""
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for p in partes:
        c = Vector(p[1])
        if p[0] == "box":
            meio = Vector(p[2]) / 2
        else:
            r = p[2][0]
            meio = Vector((r, r, r))
        for i in range(3):
            mn[i] = min(mn[i], c[i] - meio[i])
            mx[i] = max(mx[i], c[i] + meio[i])
    centro = (mn + mx) / 2
    centro.z = mn.z
    locais = []
    for p in partes:
        novo = list(p)
        novo[1] = tuple(Vector(p[1]) - centro)
        locais.append(tuple(novo))
    return malha(nome, locais, col, loc=tuple(centro))


def caixa(nome, minimo, maximo, mat, col):
    return objeto_mundo(nome, [BX(minimo, maximo, mat)], col)


def parede(nome, eixo, ini, fim, pos, esp, altura, mat, col, aberturas=()):
    """Parede reta com vãos.
    eixo='X': corre ao longo de X (de ini a fim) centrada em Y=pos.
    eixo='Y': corre ao longo de Y centrada em X=pos.
    aberturas: lista de (inicio, fim, altura_do_vao) -> gera vergas acima."""
    trechos = []
    cursor = ini
    for a0, a1, h in sorted(aberturas):
        if a0 > cursor:
            trechos.append((cursor, a0, 0.0, altura))
        if h < altura:
            trechos.append((a0, a1, h, altura))       # verga
        cursor = a1
    if cursor < fim:
        trechos.append((cursor, fim, 0.0, altura))
    partes = []
    for s0, s1, z0, z1 in trechos:
        if eixo == "X":
            partes.append(BX((s0, pos - esp / 2, z0), (s1, pos + esp / 2, z1), mat))
        else:
            partes.append(BX((pos - esp / 2, s0, z0), (pos + esp / 2, s1, z1), mat))
    return objeto_mundo(nome, partes, col)


def viga(nome, p0, p1, larg, alt, mat, col):
    """Barra entre dois pontos (corrimãos e longarinas inclinadas)."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    ob = malha(nome, [B((0, 0, 0), (d.length, larg, alt), mat)], col)
    ob.location = (p0 + p1) / 2
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = d.to_track_quat("X", "Z")
    return ob


def l2w(x, y, rot, dx, dy):
    """Converte deslocamento local (dx, dy) girado por 'rot' para o mundo."""
    return (x + dx * cos(rot) - dy * sin(rot), y + dx * sin(rot) + dy * cos(rot))


def texto(nome, corpo, loc, rot, tamanho, mats, col, inicio_cor2=None):
    """Texto 3D (letreiros). inicio_cor2 = índice do caractere que muda
    para o 2º material (ex.: "Saúde" em verde)."""
    cu = bpy.data.curves.new(nome, "FONT")
    cu.body = corpo
    cu.size = tamanho
    cu.extrude = 0.006
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    for m in mats:
        cu.materials.append(m)
    if inicio_cor2 is not None and len(mats) > 1:
        for i in range(inicio_cor2, len(corpo)):
            cu.body_format[i].material_index = 1
    ob = bpy.data.objects.new(nome, cu)
    ob.location = loc
    ob.rotation_euler = rot
    col.objects.link(ob)
    return ob


# Rotações de mobiliário: direção para onde a pessoa sentada OLHA
OLHA = {"+Y": 0.0, "-Y": pi, "+X": -pi / 2, "-X": pi / 2}


# =====================================================================
# 2. MATERIAIS (Principled BSDF via nodes + texturas procedurais)
# =====================================================================
ALIAS_BSDF = {   # nomes de entradas mudam entre Blender 3.x e 4.x/5.x
    "Base Color": ("Base Color",),
    "Roughness": ("Roughness",),
    "Metallic": ("Metallic",),
    "Alpha": ("Alpha",),
    "IOR": ("IOR",),
    "Transmission": ("Transmission Weight", "Transmission"),
    "Emission Color": ("Emission Color", "Emission"),
    "Emission Strength": ("Emission Strength",),
    "Coat": ("Coat Weight", "Clearcoat"),
}


def ajustar(no, nome, valor):
    for n in ALIAS_BSDF.get(nome, (nome,)):
        if n in no.inputs:
            try:
                no.inputs[n].default_value = valor
            except (TypeError, ValueError):
                pass
            return


def configurar_transparencia(mat):
    """Transparência compatível com EEVEE Legacy, EEVEE Next e Cycles."""
    for attr, valor in (("surface_render_method", "BLENDED"),
                        ("blend_method", "BLEND"),
                        ("shadow_method", "HASHED"),
                        ("show_transparent_back", False),
                        ("use_screen_refraction", True)):
        if hasattr(mat, attr):
            try:
                setattr(mat, attr, valor)
            except (TypeError, ValueError, AttributeError):
                pass
    mat.use_backface_culling = False


def material_base(nome, cor, rough=0.5, metal=0.0, alpha=1.0, transm=0.0,
                  ior=1.45, emissao=None, forca=0.0, coat=0.0):
    mat = bpy.data.materials.get(nome) or bpy.data.materials.new(nome)
    if mat.node_tree is None:          # Blender 3.x/4.x (no 5.x os nodes já existem)
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    saida = nt.nodes.new("ShaderNodeOutputMaterial")
    saida.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "BSDF"
    nt.links.new(bsdf.outputs[0], saida.inputs["Surface"])
    c = lin(cor)
    ajustar(bsdf, "Base Color", c)
    ajustar(bsdf, "Roughness", rough)
    ajustar(bsdf, "Metallic", metal)
    ajustar(bsdf, "Alpha", alpha)
    ajustar(bsdf, "Transmission", transm)
    ajustar(bsdf, "IOR", ior)
    ajustar(bsdf, "Coat", coat)
    if emissao:
        ajustar(bsdf, "Emission Color", lin(emissao))
        ajustar(bsdf, "Emission Strength", forca)
    # Cor no modo Solid da viewport
    mat.diffuse_color = (c[0], c[1], c[2], alpha)
    mat.roughness = rough
    mat.metallic = metal
    if alpha < 1.0 or transm > 0.0:
        configurar_transparencia(mat)
    return mat


def _nos(mat):
    nt = mat.node_tree
    return nt, nt.nodes["BSDF"]


def mat_piso_vinilico():
    """Piso vinílico em réguas (1.22 x 0.185 m) cinza claro – Brick Texture."""
    mat = material_base("DS_Piso_Vinilico_Cinza", "#C9CCCD", rough=0.42)
    nt, bsdf = _nos(mat)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    reguas = nt.nodes.new("ShaderNodeTexBrick")
    reguas.offset = 0.5
    reguas.offset_frequency = 2
    for k, v in (("Color1", lin("#CDD0D1")), ("Color2", lin("#BDC1C3")),
                 ("Mortar", lin("#A2A7AA")), ("Scale", 1.0),
                 ("Mortar Size", 0.003), ("Bias", 0.0),
                 ("Brick Width", 1.22), ("Row Height", 0.185)):
        ajustar(reguas, k, v)
    relevo = nt.nodes.new("ShaderNodeBump")
    ajustar(relevo, "Strength", 0.25)
    ajustar(relevo, "Distance", 0.002)
    nt.links.new(coord.outputs["Object"], reguas.inputs["Vector"])
    nt.links.new(reguas.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(reguas.outputs["Fac"], relevo.inputs["Height"])
    nt.links.new(relevo.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mat_parede():
    """Tinta acrílica fosca clara com barrado cinza-azulado até 1.10 m."""
    mat = material_base("DS_Parede_Tinta_Fosca", COR["branco_gelo"], rough=0.9)
    nt, bsdf = _nos(mat)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    maior = nt.nodes.new("ShaderNodeMath")
    maior.operation = "GREATER_THAN"
    maior.inputs[1].default_value = ALTURA_BARRADO
    rampa = nt.nodes.new("ShaderNodeValToRGB")
    rampa.color_ramp.interpolation = "CONSTANT"
    rampa.color_ramp.elements[0].color = lin(COR["cinza_barrado"])
    rampa.color_ramp.elements[1].position = 0.5
    rampa.color_ramp.elements[1].color = lin(COR["branco_gelo"])
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], maior.inputs[0])
    nt.links.new(maior.outputs[0], rampa.inputs["Fac"])
    nt.links.new(rampa.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def mat_veios(nome, cor_clara, cor_veio, escala, distorcao, rough, pos_veio):
    """Madeira / mármore procedurais (Wave Texture + Color Ramp)."""
    mat = material_base(nome, cor_clara, rough=rough)
    nt, bsdf = _nos(mat)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    onda = nt.nodes.new("ShaderNodeTexWave")
    onda.wave_type = "BANDS"
    try:
        onda.bands_direction = "X"
    except AttributeError:
        pass
    for k, v in (("Scale", escala), ("Distortion", distorcao),
                 ("Detail", 4.0), ("Detail Scale", 1.5)):
        ajustar(onda, k, v)
    rampa = nt.nodes.new("ShaderNodeValToRGB")
    rampa.color_ramp.elements[0].color = lin(cor_veio)
    rampa.color_ramp.elements[1].position = pos_veio
    rampa.color_ramp.elements[1].color = lin(cor_clara)
    nt.links.new(coord.outputs["Object"], onda.inputs["Vector"])
    nt.links.new(onda.outputs["Fac"], rampa.inputs["Fac"])
    nt.links.new(rampa.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def criar_materiais():
    # --- Acabamentos ---
    M["piso"] = mat_piso_vinilico()
    M["parede"] = mat_parede()
    M["parede_ext"] = material_base("DS_Parede_Externa", "#C3C7C8", rough=0.85)
    M["forro"] = material_base("DS_Forro_Gesso", "#FAFAF8", rough=0.95)
    M["calcada"] = material_base("DS_Calcada_Concreto", "#A7A39B", rough=0.95)
    M["piso_tatil"] = material_base("DS_Piso_Tatil", "#E3B21B", rough=0.8)
    M["asfalto"] = material_base("DS_Asfalto", "#3A3B3C", rough=0.95)
    # --- Vidros (técnico incolor e jateado para privacidade) ---
    M["vidro"] = material_base("DS_Vidro_Incolor", "#E8F4F6", rough=0.02,
                               alpha=0.15, transm=1.0, ior=1.52)
    M["vidro_jateado"] = material_base("DS_Vidro_Jateado", "#F4F8FA", rough=0.45,
                                       alpha=0.55, transm=0.9, ior=1.52)
    M["porta_fume"] = material_base("DS_Porta_Vidro_Fume", "#141618", rough=0.08, coat=1.0)
    # --- Madeiras, mármore e metais ---
    M["madeira"] = mat_veios("DS_Madeira_Carvalho", "#C9A06C", "#9C7246", 9.0, 5.0, 0.45, 0.85)
    M["madeira_escura"] = mat_veios("DS_Madeira_Escura_Degraus", "#6B4029", "#4A2A1A", 7.0, 4.0, 0.4, 0.8)
    M["marmore"] = mat_veios("DS_Marmore_Branco", "#F4F4F1", "#8D9398", 1.3, 14.0, 0.15, 0.10)
    M["aluminio"] = material_base("DS_Aluminio_Anodizado", "#C9CCCF", rough=0.3, metal=1.0)
    M["metal_branco"] = material_base("DS_Aco_Pintado_Branco", "#F0F0EE", rough=0.35, metal=0.2)
    M["branco_laca"] = material_base("DS_Laca_Branca", "#F5F5F3", rough=0.3)
    M["preto"] = material_base("DS_Preto_Fosco", "#1A1A1A", rough=0.6)
    M["louca"] = material_base("DS_Louca_Branca", "#FFFFFF", rough=0.1, coat=0.5)
    # --- Cores institucionais Descont'Saúde ---
    M["azul"] = material_base("DS_Azul_Institucional", COR["azul_marinho"], rough=0.6)
    M["ciano"] = material_base("DS_Azul_Ciano", COR["azul_ciano"], rough=0.5)
    M["turquesa"] = material_base("DS_Turquesa_Acolhimento", COR["turquesa"], rough=0.6)
    M["verde"] = material_base("DS_Verde_Lima_Institucional", COR["verde_lima"], rough=0.55)
    M["grafite"] = material_base("DS_Grafite_Fachada", COR["grafite"], rough=0.5)
    M["texto_branco"] = material_base("DS_Texto_Branco", "#FFFFFF", rough=0.4)
    # --- Estofados ---
    M["estofado_azul"] = material_base("DS_Estofado_Azul_Marinho", "#16376B", rough=0.85)
    M["estofado_turquesa"] = material_base("DS_Estofado_Turquesa", "#2A9D93", rough=0.85)
    M["estofado_verde"] = material_base("DS_Estofado_Verde_Lima", "#7DB33A", rough=0.9)
    M["maca"] = material_base("DS_Maca_Courvin", "#1D5F86", rough=0.5)
    # --- Iluminação, telas e vegetação ---
    M["led"] = material_base("DS_LED_Emissivo", "#FFFFFF", rough=0.5,
                             emissao="#FFF4E5", forca=12.0)
    M["tela"] = material_base("DS_Tela_TV", "#0A2A55", rough=0.15,
                              emissao="#1B5FA8", forca=1.5)
    M["folha"] = material_base("DS_Folhagem", "#3E7D3A", rough=0.7)
    M["vaso"] = material_base("DS_Vaso_Ceramica", "#E9E4DA", rough=0.6)


# =====================================================================
# 3. PAREDES, DIVISÓRIAS, PISO, FORRO E FACHADA
# =====================================================================
def construir_paredes(col):
    P, H = M["parede"], PE_DIREITO
    # --- Perímetro do hall (paredes externas / de divisa) ---
    parede("Parede_Externa_Esquerda", "Y", -0.25, PROF_HALL + 0.10,
           -E_EXT / 2, E_EXT, TOPO_LAJE, P, col)
    parede("Parede_Externa_Direita", "Y", -0.25, PROF_HALL + 0.10,
           LARG_HALL + E_EXT / 2, E_EXT, TOPO_LAJE, P, col)
    # --- Fundo do hall (lados da Sala 01) ---
    parede("Parede_Fundo_Hall_Esquerda", "X", 0.0, SALA_X0 - E_INT,
           PROF_HALL + E_INT / 2, E_INT, H, P, col)
    parede("Parede_Fundo_Hall_Direita_Garagem", "X", SALA_X1 + E_INT, LARG_HALL,
           PROF_HALL + E_INT / 2, E_INT, H, P, col,
           aberturas=[(6.75, 7.65, 2.10)])
    caixa("Porta_Acesso_Garagem", (6.75, PROF_HALL + 0.02, 0.0),
          (7.65, PROF_HALL + 0.08, 2.10), M["porta_fume"], col)
    # --- Consultórios (antiga Sala 01) ---
    parede("Consultorios_Parede_Esquerda", "Y", SALA_Y0, SALA_Y1 + E_INT,
           SALA_X0 - E_INT / 2, E_INT, H, P, col)
    parede("Consultorios_Parede_Direita", "Y", SALA_Y0, SALA_Y1 + E_INT,
           SALA_X1 + E_INT / 2, E_INT, H, P, col)
    parede("Consultorios_Parede_Fundo", "X", SALA_X0 - E_INT, SALA_X1 + E_INT,
           SALA_Y1 + E_INT / 2, E_INT, H, P, col)
    parede("Divisoria_Drywall_Acustica_C01_C02", "Y", SALA_Y0 + 0.02, SALA_Y1,
           (DIV_X0 + DIV_X1) / 2, E_DIV, H, P, col)
    # --- Lavabo existente (porta 0.70 x 2.10 voltada para o hall) ---
    parede("Lavabo_Parede_Frontal", "X", LAV_X0, LAV_X1,
           LAV_Y0 + E_INT / 2, E_INT, H, P, col)
    parede("Lavabo_Parede_Fundo", "X", LAV_X0, LAV_X1,
           LAV_Y1 - E_INT / 2, E_INT, H, P, col)
    parede("Lavabo_Parede_Lateral", "Y", LAV_Y0 + E_INT, LAV_Y1 - E_INT,
           LAV_X0 + E_INT / 2, E_INT, H, P, col,
           aberturas=[(5.15, 5.85, 2.10)])
    caixa("Lavabo_Porta_Aberta", (LAV_X0 + E_INT + 0.01, 5.13, 0.0),
          (LAV_X0 + E_INT + 0.71, 5.17, 2.10), M["madeira"], col)


def construir_vidros(col):
    """Fachada da Sala 01: bandeira 5.00x1.45 incolor + painéis jateados
    (privacidade dos consultórios) + portas de vidro abertas."""
    y = SALA_Y0
    al, v, vj = M["aluminio"], M["vidro"], M["vidro_jateado"]
    # Esquadria de alumínio (montantes e travessas)
    perfis = [BX((SALA_X0, y - 0.03, 2.30), (SALA_X1, y + 0.03, 2.35), al),          # travessa
              BX((SALA_X0, y - 0.03, PE_DIREITO - 0.03), (SALA_X1, y + 0.03, PE_DIREITO), al),
              BX((2.45, y - 0.03, 0.0), (2.49, y + 0.03, 2.30), al),                  # batente C01
              BX((DIV_X0, y - 0.03, 0.0), (DIV_X1, y + 0.03, PE_DIREITO), al),        # encontro divisória
              BX((4.81, y - 0.03, 0.0), (4.85, y + 0.03, 2.30), al),                  # batente C02
              BX((SALA_X1 - 0.04, y - 0.03, 0.0), (SALA_X1, y + 0.03, 2.30), al),
              BX((2.49, y - 0.03, 0.0), (DIV_X0, y + 0.03, 0.04), al),                # rodapé
              BX((4.85, y - 0.03, 0.0), (SALA_X1 - 0.04, y + 0.03, 0.04), al)]
    objeto_mundo("Consultorios_Esquadria_Aluminio", perfis, col)
    caixa("Vidro_Bandeira_Incolor_5.00x1.45", (SALA_X0, y - 0.01, 2.35),
          (SALA_X1, y + 0.01, PE_DIREITO - 0.03), v, col)
    caixa("Vidro_Jateado_Consultorio_01", (2.49, y - 0.01, 0.04),
          (DIV_X0, y + 0.01, 2.30), vj, col)
    caixa("Vidro_Jateado_Consultorio_02", (4.85, y - 0.01, 0.04),
          (SALA_X1 - 0.04, y + 0.01, 2.30), vj, col)
    # Portas de vidro jateado (abertas 90° para dentro, encostadas na parede)
    for nome, x0, larg in (("Porta_Consultorio_01_1.10x2.30", SALA_X0 + 0.04, 1.10),
                           ("Porta_Consultorio_02_0.90x2.30", DIV_X1 + 0.04, 0.90)):
        objeto_mundo(nome, [
            BX((x0, y + 0.03, 0.01), (x0 + 0.04, y + 0.03 + larg, 2.29), vj),
            BX((x0 + 0.04, y + larg - 0.10, 0.85), (x0 + 0.07, y + larg - 0.07, 1.25), al),
        ], col)
    # Identificação das salas na bandeira (faces voltadas para o hall)
    for n, xm in (("01", (SALA_X0 + DIV_X0) / 2), ("02", (DIV_X1 + SALA_X1) / 2)):
        texto(f"Placa_Consultorio_{n}", f"CONSULTÓRIO {n}", (xm, y - 0.025, 2.55),
              (radians(90), 0, 0), 0.14, [M["azul"]], col)


def construir_piso_forro(col_piso, col_forro):
    caixa("Piso_Vinilico_Cinza_Claro", (-E_EXT, -0.25, -0.05),
          (LARG_HALL + E_EXT, SALA_Y1 + E_INT, 0.0), M["piso"], col_piso)
    # Calçada, piso tátil e rua (contexto externo)
    caixa("Calcada", (-3.0, -4.0, -0.12), (LARG_HALL + 3.0, -0.25, 0.0), M["calcada"], col_piso)
    caixa("Calcada_Piso_Tatil_Direcional", (-3.0, -1.60, 0.0),
          (LARG_HALL + 3.0, -1.35, 0.004), M["piso_tatil"], col_piso)
    caixa("Rua_Asfalto", (-3.0, -12.0, -0.30), (LARG_HALL + 3.0, -4.0, -0.15), M["asfalto"], col_piso)
    # Forro de gesso + laje (com o vão da escada recortado)
    furo_y0, furo_y1 = 4.10, PAT_Y1 + 0.07
    z0, z1 = PE_DIREITO, TOPO_LAJE
    objeto_mundo("Forro_Gesso_Hall", [
        BX((0.0, 0.0, z0), (LARG_HALL, furo_y0, z1), M["forro"]),
        BX((L2_X1, furo_y0, z0), (LARG_HALL, furo_y1, z1), M["forro"]),
        BX((0.0, furo_y1, z0), (LARG_HALL, PROF_HALL, z1), M["forro"]),
    ], col_forro)
    caixa("Forro_Gesso_Consultorios", (SALA_X0, SALA_Y0, z0),
          (SALA_X1, SALA_Y1, z1), M["forro"], col_forro)


def construir_fachada(col):
    pe = M["parede_ext"]
    # Pilares, verga da porta de enrolar e parede superior
    objeto_mundo("Fachada_Pilares_Verga", [
        BX((-E_EXT, -0.25, 0.0), (0.30, 0.0, TOPO_LAJE), pe),
        BX((LARG_HALL - 0.30, -0.25, 0.0), (LARG_HALL + E_EXT, 0.0, TOPO_LAJE), pe),
        BX((0.30, -0.20, 2.90), (LARG_HALL - 0.30, 0.0, TOPO_LAJE), M["parede"]),
        BX((-E_EXT, -0.25, TOPO_LAJE), (LARG_HALL + E_EXT, 0.0, 4.80), pe),
    ], col)
    # Letreiro em ACM grafite (como no render da fachada)
    caixa("Fachada_Letreiro_ACM", (-E_EXT, -0.32, 2.95),
          (LARG_HALL + E_EXT, -0.25, 4.75), M["grafite"], col)
    caixa("Fachada_Faixa_Verde", (1.0, -0.335, 3.24),
          (LARG_HALL - 0.2, -0.32, 3.27), M["verde"], col)
    texto("Fachada_Texto_DescontSaude", "Descont'Saúde", (4.45, -0.335, 4.00),
          (radians(90), 0, 0), 0.62, [M["texto_branco"], M["verde"]], col, inicio_cor2=8)
    texto("Fachada_Texto_Servicos", "CONSULTAS  |  EXAMES  |  ODONTOLOGIA",
          (4.45, -0.335, 3.45), (radians(90), 0, 0), 0.17, [M["texto_branco"]], col)
    logo_placeholder("Fachada_Logo_Placeholder", (0.75, -0.34, 3.95), 2.6, "Y", col)
    # Vitrine: caixilhos, vidros fixos e porta dupla (aberta para fora)
    y, al = 0.0, M["aluminio"]
    perfis = [BX((0.30, y - 0.05, 0.0), (3.15, y + 0.01, 0.04), al),
              BX((4.75, y - 0.05, 0.0), (LARG_HALL - 0.30, y + 0.01, 0.04), al),
              BX((0.30, y - 0.05, 2.86), (LARG_HALL - 0.30, y + 0.01, 2.90), al),
              BX((3.15, y - 0.05, 2.30), (4.75, y + 0.01, 2.34), al)]
    for xm in (0.30, 1.72, 3.13, 4.73, 6.13, LARG_HALL - 0.35):
        perfis.append(BX((xm, y - 0.05, 0.0), (xm + 0.05, y + 0.01, 2.90), al))
    objeto_mundo("Fachada_Caixilhos_Aluminio", perfis, col)
    objeto_mundo("Fachada_Vidros_Fixos", [
        BX((0.30, y - 0.03, 0.04), (3.15, y - 0.01, 2.86), M["vidro"]),
        BX((4.75, y - 0.03, 0.04), (LARG_HALL - 0.30, y - 0.01, 2.86), M["vidro"]),
        BX((3.15, y - 0.03, 2.34), (4.75, y - 0.01, 2.86), M["vidro"]),
    ], col)
    for nome, x0 in (("Fachada_Porta_Vidro_Esquerda", 3.18), ("Fachada_Porta_Vidro_Direita", 4.69)):
        objeto_mundo(nome, [
            BX((x0, -0.83, 0.02), (x0 + 0.03, -0.05, 2.28), M["vidro"]),
            BX((x0 - 0.03, -0.78, 0.80), (x0 + 0.06, -0.75, 1.70), al),
        ], col)


def logo_placeholder(nome, centro, escala, normal, col):
    """Símbolo simplificado da marca: 4 pétalas (cruz da saúde) nas cores
    institucionais + 3 pontos azuis (as pessoas acolhidas)."""
    d, r, esp = 0.09 * escala, 0.075 * escala, 0.02
    eixo = "X" if normal == "X" else "Y"

    def pos(h, v):
        return (0, h, v) if normal == "X" else (h, 0, v)

    partes = []
    for (h, v), m in zip(((0, 1), (1, 0), (0, -1), (-1, 0)),
                         (M["turquesa"], M["ciano"], M["azul"], M["verde"])):
        partes.append(CY(pos(h * d, v * d), r, esp, m, eixo))
    for h in (-1.2, 0.0, 1.2):
        partes.append(CY(pos(h * d, -2.0 * d - (0.3 * d if h == 0 else 0)),
                         0.028 * escala, esp, M["azul"], eixo))
    return malha(nome, partes, col, loc=centro)


# =====================================================================
# 4. ESCADA (22 degraus em "L" – estrutura metálica branca, piso madeira)
# =====================================================================
def construir_escada(col):
    mad, aco = M["madeira_escura"], M["metal_branco"]
    degraus = []
    for i in range(1, N_LANCE1 + 1):                        # lance 1 (+Y)
        y0 = ESC_Y0 + (i - 1) * PISO_DEG
        z = i * ESPELHO
        degraus.append(BX((0.02, y0, z - 0.04), (ESC_LARG - 0.02, y0 + PISO_DEG, z), mad))
    degraus.append(BX((0.02, PAT_Y0, PAT_Z - 0.10), (ESC_LARG, PAT_Y1, PAT_Z), mad))  # patamar
    for k in range(N_LANCE2):                                # lance 2 (+X)
        x0 = L2_X0 + k * PISO_DEG
        z = (N_LANCE1 + 2 + k) * ESPELHO
        degraus.append(BX((x0, PAT_Y0 + 0.02, z - 0.04), (x0 + PISO_DEG, PAT_Y1 - 0.02, z), mad))
    objeto_mundo("Escada_Degraus_Madeira", degraus, col)

    # Longarinas metálicas inclinadas
    for n, x in (("Parede", 0.05), ("Livre", ESC_LARG - 0.05)):
        viga(f"Escada_Longarina_Lance1_{n}", (x, ESC_Y0, 0.0),
             (x, PAT_Y0, PAT_Z - 0.10), 0.06, 0.22, aco, col)
    for n, y in (("Frente", PAT_Y0 + 0.05), ("Fundo", PAT_Y1 - 0.05)):
        viga(f"Escada_Longarina_Lance2_{n}", (L2_X0, y, PAT_Z - 0.10),
             (L2_X1, y, TOPO_LAJE - 0.10), 0.06, 0.22, aco, col)
    caixa("Escada_Pilar_Metalico", (ESC_LARG - 0.10, PAT_Y1 - 0.10, 0.0),
          (ESC_LARG, PAT_Y1, PAT_Z - 0.10), aco, col)

    # Guarda-corpo de tubos horizontais (como nas fotos)
    for h in (0.35, 0.65, 0.95):
        viga(f"Escada_Guarda_Corpo_Lance1_h{int(h * 100)}",
             (ESC_LARG, ESC_Y0, ESPELHO + h), (ESC_LARG, PAT_Y0, PAT_Z + h), 0.03, 0.03, aco, col)
        viga(f"Escada_Guarda_Corpo_Patamar_h{int(h * 100)}",
             (0.0, PAT_Y1, PAT_Z + h), (ESC_LARG, PAT_Y1, PAT_Z + h), 0.03, 0.03, aco, col)
        for n, y in (("Frente", PAT_Y0), ("Fundo", PAT_Y1)):
            viga(f"Escada_Guarda_Corpo_Lance2_{n}_h{int(h * 100)}",
                 (ESC_LARG, y, PAT_Z + h), (L2_X1, y, TOPO_LAJE + h), 0.03, 0.03, aco, col)
    montantes = []
    for y in (ESC_Y0 + 0.05, (ESC_Y0 + PAT_Y0) / 2, PAT_Y0):
        z = ESPELHO + (y - ESC_Y0) / (PAT_Y0 - ESC_Y0) * (PAT_Z - ESPELHO)
        montantes.append(BX((ESC_LARG - 0.02, y - 0.02, z - 0.05), (ESC_LARG + 0.02, y + 0.02, z + 0.96), aco))
    for x in (0.05, ESC_LARG):
        montantes.append(BX((x - 0.02, PAT_Y1 - 0.02, PAT_Z), (x + 0.02, PAT_Y1 + 0.02, PAT_Z + 0.96), aco))
    for x in ((L2_X0 + L2_X1) / 2, L2_X1 - 0.03):
        z = PAT_Z + (x - L2_X0) / (L2_X1 - L2_X0) * (TOPO_LAJE - PAT_Z)
        for y in (PAT_Y0, PAT_Y1):
            montantes.append(BX((x - 0.02, y - 0.02, z - 0.05), (x + 0.02, y + 0.02, z + 0.96), aco))
    objeto_mundo("Escada_Montantes_Guarda_Corpo", montantes, col)


# =====================================================================
# 5. MOBILIÁRIO (placeholders primitivos nomeados)
#    Convenção local: a pessoa sentada olha para +Y local.
# =====================================================================
def cadeira_fixa(nome, x, y, olha, estofado, col):
    met = M["aluminio"]
    partes = [B((0, 0, 0.45), (0.46, 0.46, 0.06), estofado),
              B((0, -0.21, 0.76), (0.46, 0.05, 0.40), estofado)]
    for sx in (-0.20, 0.20):
        for sy in (-0.20, 0.20):
            partes.append(B((sx, sy, 0.21), (0.025, 0.025, 0.42), met))
        partes.append(B((sx, -0.22, 0.52), (0.025, 0.025, 0.14), met))
    return malha(nome, partes, col, loc=(x, y, 0), rot_z=OLHA[olha])


def cadeira_giratoria(nome, x, y, olha, estofado, col):
    met, pr = M["aluminio"], M["preto"]
    partes = [B((0, 0, 0.48), (0.50, 0.48, 0.08), estofado),
              B((0, -0.25, 0.90), (0.46, 0.06, 0.55), estofado),
              B((0, -0.25, 0.58), (0.06, 0.04, 0.20), met),
              CY((0, 0, 0.26), 0.03, 0.36, met),
              B((0, 0, 0.06), (0.62, 0.05, 0.04), met),
              B((0, 0, 0.06), (0.05, 0.62, 0.04), met)]
    for sx in (-0.27, 0.27):
        partes.append(B((sx, 0.0, 0.70), (0.05, 0.30, 0.04), pr))
        partes.append(B((sx, -0.05, 0.61), (0.03, 0.03, 0.14), met))
    return malha(nome, partes, col, loc=(x, y, 0), rot_z=OLHA[olha])


def poltrona(nome, x, y, olha, col):
    est = M["estofado_azul"]
    partes = [B((0, 0.03, 0.30), (0.78, 0.70, 0.24), est),
              B((0, -0.30, 0.62), (0.78, 0.16, 0.40), est),
              B((0, -0.17, 0.57), (0.36, 0.10, 0.28), M["estofado_verde"])]   # almofada
    for sx in (-0.33, 0.33):
        partes.append(B((sx, 0.03, 0.52), (0.12, 0.70, 0.20), est))
        for sy in (-0.28, 0.30):
            partes.append(B((sx, sy, 0.09), (0.04, 0.04, 0.18), M["madeira"]))
    return malha(nome, partes, col, loc=(x, y, 0), rot_z=OLHA[olha])


def longarina(nome, x, y, olha, n_lugares, estofado, col):
    """Longarina de espera (assentos conjugados)."""
    met, passo = M["aluminio"], 0.55
    comp = n_lugares * passo
    partes = [B((0, -0.05, 0.40), (comp, 0.06, 0.05), met)]
    for i in range(n_lugares):
        ox = (i - (n_lugares - 1) / 2) * passo
        partes += [B((ox, 0, 0.45), (0.48, 0.46, 0.05), estofado),
                   B((ox, -0.22, 0.75), (0.48, 0.04, 0.36), estofado),
                   B((ox, -0.21, 0.52), (0.04, 0.03, 0.12), met)]
    for lx in (-(comp / 2 - 0.15), comp / 2 - 0.15):
        partes += [B((lx, -0.05, 0.20), (0.05, 0.05, 0.38), met),
                   B((lx, -0.05, 0.02), (0.06, 0.55, 0.04), met)]
    return malha(nome, partes, col, loc=(x, y, 0), rot_z=OLHA[olha])


def mesa(nome, x, y, olha, larg, prof, col):
    """Mesa de atendimento: o usuário (médico/consultor) senta no lado +Y local
    e olha para -Y local. 'olha' = direção para onde o USUÁRIO olha."""
    tampo, est = M["madeira"], M["branco_laca"]
    partes = [B((0, 0, 0.735), (larg, prof, 0.03), tampo),
              B((0, -prof / 2 + 0.10, 0.45), (larg - 0.06, 0.02, 0.40), est),   # painel frontal
              B((larg / 2 - 0.24, 0.02, 0.33), (0.40, prof - 0.12, 0.60), est)]  # gaveteiro
    for sx in (-1, 1):
        partes.append(B((sx * (larg / 2 - 0.015), 0, 0.36), (0.03, prof - 0.02, 0.72), est))
    rot = OLHA[olha] + pi
    return malha(nome, partes, col, loc=(x, y, 0), rot_z=rot), rot


def monitor(nome, x, y, rot, col, z=0.75):
    pr = M["preto"]
    partes = [B((0, 0, 0.28), (0.55, 0.025, 0.33), pr),
              B((0, 0.014, 0.28), (0.52, 0.002, 0.30), M["tela"]),
              B((0, -0.03, 0.08), (0.05, 0.03, 0.16), pr),
              B((0, -0.03, 0.005), (0.22, 0.18, 0.01), pr)]
    return malha(nome, partes, col, loc=(x, y, z), rot_z=rot)


def notebook(nome, x, y, rot, col):
    partes = [B((0, 0, 0.76), (0.34, 0.24, 0.02), M["aluminio"]),
              B((0, -0.12, 0.88), (0.34, 0.01, 0.22), M["preto"])]
    return malha(nome, partes, col, loc=(x, y, 0), rot_z=rot)


def maca(nome, x, y, col):
    """Maca de exames 1.85 x 0.65 x 0.80 m com cabeceira elevada."""
    met = M["metal_branco"]
    partes = [B((0, 0, 0.76), (1.85, 0.65, 0.08), M["maca"]),
              B((-0.72, 0, 0.86), (0.40, 0.62, 0.10), M["maca"]),
              B((0, 0, 0.68), (1.80, 0.60, 0.06), met),
              B((0, 0, 0.18), (1.70, 0.55, 0.02), met)]
    for sx in (-0.85, 0.85):
        for sy in (-0.27, 0.27):
            partes.append(B((sx, sy, 0.33), (0.04, 0.04, 0.66), met))
    return malha(nome, partes, col, loc=(x, y, 0))


def escadinha(nome, x, y, col):
    """Escada de 2 degraus para acesso à maca (sobe em direção a +Y)."""
    partes = [B((0, -0.075, 0.19), (0.40, 0.15, 0.03), M["preto"]),
              B((0, 0.075, 0.39), (0.40, 0.15, 0.03), M["preto"])]
    for sx in (-0.19, 0.19):
        partes.append(B((sx, 0, 0.20), (0.02, 0.30, 0.40), M["metal_branco"]))
    return malha(nome, partes, col, loc=(x, y, 0))


def mocho(nome, x, y, col):
    met = M["aluminio"]
    partes = [CY((0, 0, 0.58), 0.19, 0.07, M["maca"]),
              CY((0, 0, 0.30), 0.025, 0.50, met),
              B((0, 0, 0.04), (0.55, 0.05, 0.04), met),
              B((0, 0, 0.04), (0.05, 0.55, 0.04), met)]
    return malha(nome, partes, col, loc=(x, y, 0))


def lavatorio(nome, x, y, olha, col):
    """Lavatório clínico com gabinete (encostado na parede atrás: -Y local)."""
    partes = [B((0, 0, 0.40), (0.50, 0.45, 0.80), M["branco_laca"]),
              B((0, 0, 0.83), (0.52, 0.47, 0.06), M["louca"]),
              B((0, -0.17, 0.93), (0.03, 0.03, 0.14), M["aluminio"]),
              B((0, -0.11, 0.99), (0.03, 0.12, 0.02), M["aluminio"])]
    return malha(nome, partes, col, loc=(x, y, 0), rot_z=OLHA[olha])


def planta(nome, x, y, col):
    partes = [CY((0, 0, 0.25), 0.20, 0.50, M["vaso"]),
              SP((0, 0, 0.85), 0.33, M["folha"]),
              SP((0.10, 0.08, 1.10), 0.24, M["folha"]),
              SP((-0.08, -0.06, 1.05), 0.26, M["folha"])]
    return malha(nome, partes, col, loc=(x, y, 0))


# ---------------------------------------------------------------------
def mobiliario_recepcao(col):
    """Recepção (balcão existente junto à parede direita) + sala de espera."""
    mm, md = M["marmore"], M["madeira"]
    X0, XW, Y0, YA, Y1 = 6.20, 7.10, 1.40, 2.30, 3.80
    objeto_mundo("Recepcao_Balcao_Atendimento_Ergonomico", [
        # Trecho acessível NBR 9050 (h = 0.80 m, 0.90 m livre, vão p/ joelhos)
        BX((6.10, Y0, 0.76), (XW, YA, 0.80), mm),
        BX((6.42, Y0 + 0.04, 0.0), (6.45, YA, 0.76), mm),
        BX((6.10, Y0, 0.0), (XW, Y0 + 0.04, 0.76), mm),
        # Trecho alto: frente 1.10 m (apoio) + mesa de trabalho 0.75 m
        BX((X0, YA, 0.0), (6.45, Y1, 1.05), mm),
        BX((6.15, YA - 0.02, 1.05), (6.55, Y1, 1.10), md),
        BX((6.45, YA, 0.72), (XW, Y1, 0.75), md),
        BX((X0, Y1 - 0.04, 0.0), (XW, Y1, 1.05), mm),
        BX((6.55, 3.15, 0.0), (7.00, 3.70, 0.60), M["branco_laca"]),         # gaveteiro
        BX((X0 - 0.015, YA, 0.12), (X0, Y1, 0.16), M["verde"]),              # faixa da marca
    ], col)
    texto("Recepcao_Balcao_Logo", "Descont'Saúde", (X0 - 0.02, 3.05, 0.62),
          (radians(90), 0, radians(-90)), 0.15, [M["azul"], M["verde"]], col, inicio_cor2=8)
    monitor("Recepcao_Monitor_01", 6.62, 1.85, OLHA["+X"], col, z=0.80)
    monitor("Recepcao_Monitor_02", 6.62, 3.10, OLHA["+X"], col)
    cadeira_giratoria("Recepcao_Cadeira_Atendente_01", 7.42, 1.85, "-X", M["estofado_azul"], col)
    cadeira_giratoria("Recepcao_Cadeira_Atendente_02", 7.42, 3.10, "-X", M["estofado_azul"], col)

    # Painel institucional atrás da recepção
    caixa("Recepcao_Painel_Institucional_Azul", (LARG_HALL - 0.03, 1.20, 0.0),
          (LARG_HALL, 4.00, 3.00), M["azul"], col)
    caixa("Recepcao_Painel_Faixa_Verde", (LARG_HALL - 0.035, 1.20, 2.12),
          (LARG_HALL - 0.03, 4.00, 2.16), M["verde"], col)
    texto("Recepcao_Painel_Texto", "Descont'Saúde", (LARG_HALL - 0.04, 2.80, 2.50),
          (radians(90), 0, radians(-90)), 0.26, [M["texto_branco"], M["verde"]], col, inicio_cor2=8)
    logo_placeholder("Recepcao_Painel_Logo", (LARG_HALL - 0.045, 1.55, 2.55), 1.0, "X", col)

    # Pendentes globo sobre o balcão (como nas fotos)
    pend = []
    for yp in (1.85, 2.60, 3.35):
        pend += [CY((6.32, yp, (2.55 + PE_DIREITO) / 2), 0.004, PE_DIREITO - 2.55, M["preto"]),
                 CY((6.32, yp, 2.56), 0.15, 0.02, M["preto"]),
                 SP((6.32, yp, 2.42), 0.12, M["led"])]
    objeto_mundo("Recepcao_Pendentes_Globo", pend, col)

    # Sala de espera: 2 longarinas de 3 lugares junto à escada + estar na vitrine
    longarina("Espera_Longarina_3L_A", 1.65, 2.65, "+X", 3, M["estofado_turquesa"], col)
    longarina("Espera_Longarina_3L_B", 1.65, 4.35, "+X", 3, M["estofado_turquesa"], col)
    poltrona("Espera_Poltrona_01", 0.72, 0.85, "+X", col)
    poltrona("Espera_Poltrona_02", 2.38, 0.85, "-X", col)
    caixa("Espera_Mesa_Centro", (1.25, 0.60, 0.0), (1.85, 1.10, 0.40), M["branco_laca"], col)
    objeto_mundo("Espera_Bebedouro", [
        BX((0.18, 6.18, 0.0), (0.52, 6.52, 1.05), M["branco_laca"]),
        CY((0.35, 6.35, 1.22), 0.13, 0.34, M["vidro"]),
    ], col)
    objeto_mundo("Espera_TV_Painel_Senhas", [
        BX((LAV_X0 - 0.04, 6.02, 1.55), (LAV_X0, 6.99, 2.10), M["preto"]),
        BX((LAV_X0 - 0.045, 6.05, 1.58), (LAV_X0 - 0.04, 6.96, 2.07), M["tela"]),
    ], col)
    planta("Planta_Vitrine_Direita", 7.45, 0.55, col)
    planta("Planta_Canto_Consultorios", 0.40, 7.55, col)

    # Lavabo existente
    vaso = [CY((0, 0.05, 0.20), 0.19, 0.40, M["louca"]),
            B((0, -0.22, 0.57), (0.40, 0.16, 0.34), M["louca"]),
            B((0, 0.05, 0.415), (0.36, 0.44, 0.03), M["louca"])]
    malha("Lavabo_Vaso_Sanitario", vaso, col, loc=(7.55, 6.55, 0), rot_z=OLHA["-X"])
    lavatorio("Lavabo_Lavatorio", 6.80, 6.77, "-Y", col)


def mobiliario_vendas(col):
    """Área de atendimento de vendas: 2 estações (consultor de frente para o hall)."""
    for i, cy in ((1, 4.45), (2, 6.35)):
        cx = 5.25
        _, rot = mesa(f"Vendas_Mesa_Atendimento_{i:02d}", cx, cy, "-X", 1.20, 0.65, col)
        notebook(f"Vendas_Notebook_{i:02d}", *l2w(cx, cy, rot, 0.25, -0.12), rot, col)
        cadeira_giratoria(f"Vendas_Cadeira_Consultor_{i:02d}", *l2w(cx, cy, rot, 0, 0.62),
                          "-X", M["estofado_azul"], col)
        for j, dx in ((1, -0.30), (2, 0.30)):
            cadeira_fixa(f"Vendas_Cadeira_Cliente_{i:02d}_{j}", *l2w(cx, cy, rot, dx, -0.65),
                         "+X", M["estofado_turquesa"], col)


def mobiliario_consultorio(num, x0, x1, col):
    """Consultório: mesa médica, cadeira do médico, paciente + acompanhante,
    maca de exames, escadinha, mocho e lavatório clínico (RDC 50)."""
    xm = (x0 + x1) / 2
    cx = xm + 0.15                     # desloca a mesa para longe da porta
    _, rot = mesa(f"C{num}_Mesa_Medica", cx, 9.60, "-Y", 1.20, 0.60, col)
    monitor(f"C{num}_Monitor", *l2w(cx, 9.60, rot, -0.30, -0.15), rot, col)
    cadeira_giratoria(f"C{num}_Cadeira_Medico", cx, 10.22, "-Y", M["estofado_azul"], col)
    cadeira_fixa(f"C{num}_Cadeira_Paciente", cx - 0.30, 8.98, "+Y", M["estofado_turquesa"], col)
    cadeira_fixa(f"C{num}_Cadeira_Acompanhante", cx + 0.32, 8.98, "+Y", M["estofado_turquesa"], col)
    maca(f"C{num}_Maca_Exames", xm, SALA_Y1 - 0.45, col)
    escadinha(f"C{num}_Escadinha_2_Degraus", xm + 0.55, 11.03, col)
    mocho(f"C{num}_Mocho", x0 + 0.45, 10.95, col)
    lavatorio(f"C{num}_Lavatorio_Clinico", x0 + 0.24, 10.40, "+X", col)


# =====================================================================
# 6. ILUMINAÇÃO (luminárias LED lineares + luzes de área + sol)
# =====================================================================
def luz(nome, tipo, loc, energia, col, tamanho=(1.0, 1.0), rot=(0, 0, 0)):
    ld = bpy.data.lights.new(nome, tipo)
    ld.energy = energia
    ld.color = (1.0, 0.97, 0.92)
    if tipo == "AREA":
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = tamanho
    ob = bpy.data.objects.new(nome, ld)
    ob.location = loc
    ob.rotation_euler = rot
    col.objects.link(ob)
    return ob


def construir_iluminacao(col):
    z = PE_DIREITO - 0.015
    leds = []
    for x, y in ((2.2, 1.2), (5.6, 1.2), (2.2, 3.2), (5.6, 3.2),
                 (5.6, 5.3), (2.2, 7.0), (5.6, 7.0)):
        leds.append(BX((x - 0.75, y - 0.03, z), (x + 0.75, y + 0.03, PE_DIREITO), M["led"]))
    for xm in ((SALA_X0 + DIV_X0) / 2, (DIV_X1 + SALA_X1) / 2):
        for y in (9.4, 10.9):
            leds.append(BX((xm - 0.6, y - 0.03, z), (xm + 0.6, y + 0.03, PE_DIREITO), M["led"]))
    objeto_mundo("Luminarias_LED_Lineares", leds, col)

    for i, (x, y) in enumerate(((2.4, 2.2), (5.4, 2.2), (5.4, 5.2), (2.6, 7.0), (5.4, 7.0)), 1):
        luz(f"Luz_Hall_{i:02d}", "AREA", (x, y, PE_DIREITO - 0.10), 250, col, (2.0, 1.0))
    luz("Luz_Consultorio_01", "AREA", ((SALA_X0 + DIV_X0) / 2, 10.0, PE_DIREITO - 0.10), 200, col, (1.5, 1.5))
    luz("Luz_Consultorio_02", "AREA", ((DIV_X1 + SALA_X1) / 2, 10.0, PE_DIREITO - 0.10), 200, col, (1.5, 1.5))
    luz("Luz_Lavabo", "AREA", (7.10, 6.05, PE_DIREITO - 0.10), 60, col, (0.6, 0.6))
    luz("Sol_Fachada", "SUN", (4.0, -6.0, 10.0), 3.0, col, rot=(radians(55), 0, radians(20)))

    cena = bpy.context.scene
    mundo = cena.world or bpy.data.worlds.new("World")
    cena.world = mundo
    if mundo.node_tree is None:
        mundo.use_nodes = True
    fundo = mundo.node_tree.nodes.get("Background")
    if fundo:
        fundo.inputs[0].default_value = (0.72, 0.80, 0.90, 1.0)
        fundo.inputs[1].default_value = 0.8


# =====================================================================
# 7. CÂMERA WALKTHROUGH (olhos a 1.60 m, 24 mm, roll travado)
# =====================================================================
def construir_camera(col):
    dados = bpy.data.cameras.new("Camera_Walkthrough")
    dados.lens = 24.0                 # grande angular para interiores
    dados.sensor_width = 36.0
    dados.clip_start = 0.05
    dados.clip_end = 300.0
    cam = bpy.data.objects.new("Camera_Walkthrough_Entrada", dados)
    cam.location = (3.95, 0.55, 1.60)             # logo após a porta de entrada
    cam.rotation_euler = (radians(90), 0.0, 0.0)  # nível, olhando para o fundo (+Y)
    cam.lock_rotation = (False, True, False)      # trava o "roll" (horizonte sempre reto)
    col.objects.link(cam)

    cena = bpy.context.scene
    cena.camera = cam
    cena.unit_settings.system = "METRIC"
    cena.unit_settings.scale_length = 1.0
    cena.render.resolution_x, cena.render.resolution_y = 1920, 1080
    for motor in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            cena.render.engine = motor
            break
        except TypeError:
            continue

    # Preferências do Walk Navigation (Shift + `)
    try:
        entradas = bpy.context.preferences.inputs
        entradas.navigation_mode = "WALK"
        walk = entradas.walk_navigation
        walk.use_gravity = True       # anda "no chão"; Tab alterna
        walk.view_height = 1.60       # altura dos olhos
        walk.jump_height = 0.40
        walk.walk_speed = 1.40        # m/s (passo humano)
        walk.walk_speed_factor = 3.0
        walk.mouse_speed = 1.0
        walk.teleport_time = 0.2
    except (AttributeError, TypeError) as erro:
        print("Aviso: preferências de Walk Navigation não aplicadas:", erro)

    # Viewports 3D: olhar pela câmera em Material Preview
    wm = bpy.context.window_manager
    for janela in (wm.windows if wm else []):
        for area in janela.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for esp in area.spaces:
                if esp.type == "VIEW_3D":
                    esp.shading.type = "MATERIAL"
                    esp.shading.use_scene_lights = True
                    esp.clip_start = 0.01
                    esp.clip_end = 500.0
                    esp.lock_camera = False
                    if esp.region_3d:
                        esp.region_3d.view_perspective = "CAMERA"
    return cam


# =====================================================================
# 8. EXECUÇÃO PRINCIPAL
# =====================================================================
def main():
    limpar_cena()
    criar_materiais()

    raiz = bpy.data.collections.new(NOME_RAIZ)
    bpy.context.scene.collection.children.link(raiz)
    c = {nome: nova_colecao(nome, raiz) for nome in (
        "01_Paredes_Divisorias", "02_Vidros_Esquadrias", "03_Piso_Externo",
        "04_Forro_Laje", "05_Fachada", "06_Escada",
        "07_Recepcao_Espera", "08_Atendimento_Vendas",
        "09_Consultorio_01", "10_Consultorio_02",
        "11_Iluminacao", "12_Camera")}

    construir_paredes(c["01_Paredes_Divisorias"])
    construir_vidros(c["02_Vidros_Esquadrias"])
    construir_piso_forro(c["03_Piso_Externo"], c["04_Forro_Laje"])
    construir_fachada(c["05_Fachada"])
    construir_escada(c["06_Escada"])
    mobiliario_recepcao(c["07_Recepcao_Espera"])
    mobiliario_vendas(c["08_Atendimento_Vendas"])
    mobiliario_consultorio("01", SALA_X0, DIV_X0, c["09_Consultorio_01"])
    mobiliario_consultorio("02", DIV_X1, SALA_X1, c["10_Consultorio_02"])
    construir_iluminacao(c["11_Iluminacao"])
    construir_camera(c["12_Camera"])

    total = sum(len(col.objects) for col in c.values())
    print(f"[Descont'Saúde] Maquete gerada: {total} objetos em {len(c)} coleções.")
    print("[Descont'Saúde] Viewport na câmera -> pressione Shift + ` para caminhar.")


if __name__ == "__main__":
    main()
