"""
Names and kinds for the international organisations the World Factbook lists a country as taking part in, by the Factbook's own
abbreviations. Only the ones worth recognising at a glance are named; any other abbreviation is shown as the Factbook writes it,
never guessed at.
"""

# abbreviation: (full name, kind). Kinds: security, political, economic, other.
ORGS = {
    'UN': ('United Nations', 'political'), 'NATO': ('North Atlantic Treaty Organization', 'security'), 'EU': ('European Union', 'political'),
    'AU': ('African Union', 'political'), 'OAS': ('Organization of American States', 'political'),
    'LAS': ('Arab League', 'political'), 'CE': ('Council of Europe', 'political'), 'CIS': ('Commonwealth of Independent States', 'political'),
    'OIC': ('Organisation of Islamic Cooperation', 'political'), 'NAM': ('Non-Aligned Movement', 'political'),
    'ASEAN': ('Association of Southeast Asian Nations', 'political'), 'G-7': ('Group of Seven', 'political'),
    'G-8': ('Group of Eight', 'political'), 'G-20': ('Group of Twenty', 'political'), 'G-77': ('Group of 77', 'political'),
    'BRICS': ('BRICS (Brazil, Russia, India, China, South Africa and others)', 'political'),
    'Commonwealth': ('Commonwealth of Nations', 'political'), 'SCO': ('Shanghai Cooperation Organisation', 'security'),
    'CSTO': ('Collective Security Treaty Organization', 'security'), 'OSCE': ('Organization for Security and Co-operation in Europe', 'security'),
    'ANZUS': ('Australia, New Zealand and US security treaty', 'security'), 'EAPC': ('Euro-Atlantic Partnership Council', 'security'),
    'PFP': ('Partnership for Peace', 'security'), 'IAEA': ('International Atomic Energy Agency', 'security'),
    'OPCW': ('Organisation for the Prohibition of Chemical Weapons', 'security'), 'CTBTO': ('Comprehensive Nuclear-Test-Ban Treaty Organization', 'security'),
    'NSG': ('Nuclear Suppliers Group', 'security'), 'Australia Group': ('Australia Group (export controls on chemical and biological items)', 'security'),
    'MTCR': ('Missile Technology Control Regime', 'security'), 'Wassenaar Arrangement': ('Wassenaar Arrangement (arms export controls)', 'security'),
    'Zangger Committee': ('Zangger Committee (nuclear export controls)', 'security'), 'Interpol': ('International Criminal Police Organization', 'security'),
    'ICC': ('International Chamber of Commerce (national committees)', 'economic'), 'ICCt': ('International Criminal Court', 'political'),
    'ICJ': ('International Court of Justice', 'political'), 'UNSC': ('UN Security Council', 'security'),
    'WTO': ('World Trade Organization', 'economic'), 'IMF': ('International Monetary Fund', 'economic'),
    'IBRD': ('World Bank (International Bank for Reconstruction and Development)', 'economic'), 'OECD': ('Organisation for Economic Co-operation and Development', 'economic'),
    'OPEC': ('Organization of the Petroleum Exporting Countries', 'economic'), 'APEC': ('Asia-Pacific Economic Cooperation', 'economic'),
    'AfDB': ('African Development Bank', 'economic'), 'ADB': ('Asian Development Bank', 'economic'),
    'EBRD': ('European Bank for Reconstruction and Development', 'economic'), 'IADB': ('Inter-American Development Bank', 'economic'),
    'IEA': ('International Energy Agency', 'economic'), 'FATF': ('Financial Action Task Force', 'economic'),
    'Paris Club': ('Paris Club of creditor countries', 'economic'), 'MERCOSUR': ('Southern Common Market', 'economic'),
    'ECOWAS': ('Economic Community of West African States', 'economic'), 'SADC': ('Southern African Development Community', 'economic'),
    'GCC': ('Gulf Cooperation Council', 'economic'), 'EAEU': ('Eurasian Economic Union', 'economic'), 'EMU': ('Economic and Monetary Union (euro)', 'economic'),
    'FAO': ('Food and Agriculture Organization', 'other'), 'WHO': ('World Health Organization', 'other'),
    'UNESCO': ('UN Educational, Scientific and Cultural Organization', 'other'), 'UNHCR': ('UN High Commissioner for Refugees', 'other'),
    'UNICEF': ('UN Children\'s Fund', 'other'), 'ILO': ('International Labour Organization', 'other'),
    'IOM': ('International Organization for Migration', 'other'), 'IOC': ('International Olympic Committee', 'other'),
    'CERN': ('European Organization for Nuclear Research', 'other'), 'ESA': ('European Space Agency', 'other'),
    'WIPO': ('World Intellectual Property Organization', 'other'), 'ITU': ('International Telecommunication Union', 'other'),
    'ICAO': ('International Civil Aviation Organization', 'other'), 'IMO': ('International Maritime Organization', 'other'),
}
KIND_ORDER = ('security', 'political', 'economic', 'other')


def describe(entries):
    """[{'abbr', 'note'}] from the Factbook parser -> [{'abbr', 'name', 'kind', 'note'}], security first. An abbreviation not in
    the list above keeps its own letters as the name and the kind 'other'."""
    out = []
    for entry in entries or []:
        abbr = entry['abbr']
        name, kind = ORGS.get(abbr, (abbr, 'other'))
        out.append({'abbr': abbr, 'name': name, 'kind': kind, 'note': entry.get('note')})
    out.sort(key=lambda e: (KIND_ORDER.index(e['kind']), e['abbr'].lower()))
    return out
