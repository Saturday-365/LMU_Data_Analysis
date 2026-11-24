"""以可核验的标识识别品牌，保留 LMU 原始涂装名称。"""

import re


# 仅匹配核对过的涂装全名及组别，车队可能在不同赛事使用不同品牌。
ENTRIES = {
    ('gt3', 'garage 59 2026 #10:lm'): 'McLaren',
    ('gt3', 'united autosports 2025 #59:lm'): 'McLaren',
    ('gt3', 'team wrt 2026 #32:lm'): 'BMW',
    ('gt3', 'team wrt 2026 #32:wec'): 'BMW',
    ('gt3', 'team wrt 2026 #69:wec'): 'BMW',
    ('gt3', 'proton competition 2026 #77:lm'): 'Ford',
    ('gt3', 'proton competition 2025 #77:lm'): 'Ford',
    ('gt3', 'proton competition 2026 #75:elms'): 'Porsche',
    ('gt3', 'vista af corse 2026 #21:lm'): 'Ferrari',
    ('gt3', 'vista af corse 2026 #54:wec'): 'Ferrari',
    ('gt3', 'af corse 2026 #51:elms'): 'Ferrari',
    ('gt3', 'kessel racing 2026 #74:elms'): 'Ferrari',
    ('gt3', 'jmw motorsport 2024 2024 #66:lm'): 'Ferrari',
    ('gt3', 'akkodis asp team 2026 #87:lm'): 'Lexus',
    ('gt3', 'akkodis asp team 2026 #78:wec'): 'Lexus',
    ('gt3', 'tf sport 2026 #2:lm'): 'Chevrolet',
    ('lmp3', 'eurointernational #11:elms26'): 'Ligier',
}

ALIASES = {
    'acura': 'Acura', 'alpine': 'Alpine', 'aston martin': 'Aston Martin', 'bentley': 'Bentley',
    'audi': 'Audi', 'bmw': 'BMW', 'cadillac': 'Cadillac', 'chevrolet': 'Chevrolet', 'corvette': 'Chevrolet',
    'dallara': 'Dallara', 'ferrari': 'Ferrari', 'ford': 'Ford', 'ginetta': 'Ginetta', 'honda': 'Honda',
    'isotta fraschini': 'Isotta Fraschini', 'lamborghini': 'Lamborghini', 'lexus': 'Lexus', 'ligier': 'Ligier',
    'mclaren': 'McLaren', 'mercedes-amg': 'Mercedes-AMG', 'mercedes': 'Mercedes-AMG',
    'mustang': 'Ford', 'nissan': 'Nissan', 'oreca': 'Oreca', 'peugeot': 'Peugeot',
    'porsche': 'Porsche', 'toyota': 'Toyota', 'tvr': 'TVR',
    '丰田': 'Toyota', '保时捷': 'Porsche', '兰博基尼': 'Lamborghini', '凯迪拉克': 'Cadillac',
    '宝马': 'BMW', '宾利': 'Bentley', '梅赛德斯': 'Mercedes-AMG', '奔驰': 'Mercedes-AMG',
    '标致': 'Peugeot', '法拉利': 'Ferrari', '福特': 'Ford', '阿斯顿马丁': 'Aston Martin',
    '阿斯顿·马丁': 'Aston Martin', '雪佛兰': 'Chevrolet', '雷克萨斯': 'Lexus',
    '迈凯伦': 'McLaren', '克尔维特': 'Chevrolet', '野马': 'Ford',
}


def normalized(text):
    return ' '.join(str(text or '').casefold().split())


def named_brand(text):
    value = normalized(text).lstrip('# ')
    for alias, brand in ALIASES.items():
        matches = re.match(re.escape(alias) + r'(?=$|[\s\d\-/:·(（])', value) if alias.isascii() else value.startswith(alias)
        if matches:
            return brand
    return None


def identify_brand(metadata, model=None):
    if brand := named_brand(model):
        return brand, 'model'
    name = metadata.get('CarName')
    if brand := ENTRIES.get((normalized(metadata.get('CarClass')), normalized(name))):
        return brand, 'entry'
    if brand := named_brand(name):
        return brand, 'name'
    return None, None


def vehicle_brand(metadata, model=None, override=None):
    if override:
        if override['state'] != 'known':
            return None, 'user'
        label = override['value'].strip()
        return ALIASES.get(normalized(label), label), 'user'
    return identify_brand(metadata, model)
