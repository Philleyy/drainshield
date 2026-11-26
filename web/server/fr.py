"""
fr.py: French for the text the analysis code writes in English (processing.py, data_store.py, predictive.py...).

Those modules are shared with the Streamlit dashboard, so they stay as they are: the pages' answers are translated
here, on the way out. Fixed sentences are looked up; sentences with numbers in them are matched by pattern.
Anything not recognised is left in English rather than guessed.
"""

import re

MONTHS = dict(zip("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),
                  "janv. févr. mars avr. mai juin juill. août sept. oct. nov. déc.".split()))
DAYS = dict(zip("Mon Tue Wed Thu Fri Sat Sun".split(), "lun. mar. mer. jeu. ven. sam. dim.".split()))

# Keys whose text is shown to people. Others (category, priority, status...) are codes the site reads.
DISPLAY = {"action", "why", "recovery", "updated", "reading", "label", "task", "note", "facts", "calibrating", "head",
           "confidence", "title", "text", "verdict", "restriction", "done_text", "mode", "day"}

EXACT = {
    # what to do
    "Clean it before the rain starts": "À nettoyer avant le début de la pluie",
    "Dispatch a crew now: street flooding risk. Put up slow-down / road-closed signs: passing cars push waves "
    "toward doors and basement windows":
        "Envoyer une équipe maintenant : risque d'inondation de la rue. Installer des panneaux « Ralentir » ou "
        "« Rue fermée » : les voitures poussent des vagues vers les portes et les fenêtres de sous-sol",
    "Inspect on the next route": "Inspecter lors de la prochaine tournée",
    "Inspect the sensor": "Vérifier le capteur",
    "No action": "Aucune action",
    "No action needed": "Aucune action requise",
    "Usually clears as it warms up: check the sensor face if it lasts 6 h+":
        "Se règle d'habitude quand l'air se réchauffe : vérifier la face du capteur si ça dure plus de 6 h",
    "Vacuum / jetting needed (priority)": "Vidange / hydrocurage requis (prioritaire)",
    "Vacuum / jetting needed (schedule)": "Vidange / hydrocurage requis (à planifier)",
    "Clear the grate": "Dégager la grille",
    "Add to the next vacuum route": "Ajouter à la prochaine tournée de vidange",
    "Monitor: fine if it drains right after the rain": "Surveiller : correct s'il se vide juste après la pluie",
    "Water stuck high in dry weather: check within 24 h": "Eau haute par temps sec : vérifier d'ici 24 h",
    "No action: the sensor needs a dry, steady day to learn the outlet depth":
        "Aucune action : le capteur a besoin d'une journée sèche et stable pour apprendre la profondeur du radier",
    "Schedule a vacuum truck (non-emergency)": "Planifier un camion de vidange (non urgent)",
    "Send a vacuum / jetting crew (priority)": "Envoyer une équipe de vidange / hydrocurage (prioritaire)",
    "Clear the grate (quick street-crew job)": "Dégager la grille (travail rapide pour l'équipe de rue)",
    "Starting to drain slowly": "Commence à se vider lentement", "Draining slowly": "Se vide lentement",
    "Draining very slowly": "Se vide très lentement", "Sump filling up": "Puisard qui se remplit",
    "clear the grate": "dégager la grille", "inspect on the next route": "inspecter lors de la prochaine tournée",
    "schedule vacuum": "planifier une vidange", "vacuum / jetting, priority": "vidange / hydrocurage, prioritaire",
    "plan a vacuum": "prévoir une vidange",
    # predictions
    "No forecast (offline).": "Pas de prévision (hors ligne).",
    "No storm since installation or cleaning to learn from yet.":
        "Pas encore d'orage depuis l'installation ou le nettoyage pour apprendre.",
    # progress of an issue
    "Flagged by the sensor": "Signalé par le capteur",
    "On a run": "Ajouté à une tournée",
    "Sensor sees the sump emptied": "Le capteur voit le puisard vidé",
    "Sensor saw the sump emptied": "Le capteur a vu le puisard vidé",
    "Cleaned (logged by the crew)": "Nettoyé (inscrit par l'équipe)",
    "Inspected: no issue found": "Inspecté : aucun problème",
    "Next rain drains fast": "La prochaine pluie se vide vite",
    "Verified: the next rain drained fast": "Vérifié : la pluie suivante s'est vidée vite",
    "Still slow after cleaning: check again": "Toujours lent après le nettoyage : revérifier",
    "Sensor reporting again": "Le capteur transmet à nouveau",
    # route planner
    "Couldn't reach the online road-routing service, so drive times are estimated from straight-line distance "
    "(× 1.35 for streets).":
        "Le service d'itinéraire en ligne ne répond pas : les temps de route sont estimés à vol d'oiseau "
        "(× 1,35 pour les rues).",
    "Road line unavailable: drawn as straight segments (times are still by road).":
        "Tracé routier indisponible : dessiné en lignes droites (les temps restent calculés par la route).",
    # the basin page
    "outlet depth not known yet: the sensor is learning it": "profondeur du radier pas encore connue : le capteur l'apprend",
    "waiting for readings": "en attente de lectures",
    "Sensor offline: inspect the sensor": "Capteur hors ligne : vérifier le capteur",
    "Not draining after the rain": "Ne se vide pas après la pluie",
    "New sensor: learning the outlet depth": "Nouveau capteur : apprentissage de la profondeur du radier",
    "Normal: draining well": "Normal : se vide bien",
    "Normal: keeping up with the rain": "Normal : suit le rythme de la pluie",
    "What we saw": "Ce qu'on a vu", "Likely cause": "Cause probable", "Next step": "Prochaine étape",
    "Sensor": "Capteur",
    "Dead battery, damaged or covered sensor": "Pile à plat, capteur endommagé ou couvert",
    "Sediment covering the outlet or a partial pipe restriction":
        "Sédiments qui couvrent la sortie ou restriction partielle de la conduite",
    "Normal sediment build-up": "Accumulation normale de sédiments",
    "Grate covered (leaves, debris): water stays on the street":
        "Grille couverte (feuilles, débris) : l'eau reste dans la rue",
    "Sudden blockage: debris jammed in the trap or outlet pipe":
        "Blocage soudain : débris coincés dans la cloche ou la conduite de sortie",
    "None": "Aucun",
    "High": "élevée", "Medium": "moyenne", "Low": "faible",
    "Backing up": "Refoule", "Normal level": "Niveau normal", "Rising with the rain": "Monte avec la pluie",
    "Unknown": "Inconnu", "Not draining": "Ne se vide pas", "No live data": "Aucune donnée en direct",
    "Learning the outlet depth": "Apprentissage de la profondeur du radier",
    "Normal": "Normal", "Not tested yet": "Pas encore testé", "Slightly slow": "Légèrement lent", "Slow": "Lent",
    "Very slow": "Très lent", "Grate blocked": "Grille obstruée",
    "No recent data": "Aucune donnée récente", "No storm big enough yet": "Aucun orage assez important encore",
    "Never reported": "Aucune lecture reçue",
    "Barely rose (normal)": "A à peine monté (normal)", "No data": "Aucune donnée", "Raining now": "Pluie en cours",
    "DRY": "Sec", "WATCH": "Veille", "STORM": "Orage", "USB": "USB",
    # maintenance log
    "Crew dispatched": "Équipe envoyée", "Inspected": "Inspecté", "Obstruction found": "Obstruction trouvée",
    "Requires further investigation": "Vérification supplémentaire requise", "Cleaned / vacuumed": "Nettoyé / vidangé",
    "No issue found": "Aucun problème trouvé", "Sensor installed / re-installed": "Capteur installé / réinstallé",
    "Detected by the sensor: the sump was emptied (water dropped below the outlet)":
        "Détecté par le capteur : le puisard a été vidé (l'eau est descendue sous le radier)",
    "Added on the website": "Ajouté sur le site web",
    "Couldn't clean": "Impossible de nettoyer",
    "Obstruction found by the crew": "Obstruction trouvée par l'équipe",
    "Pilot installation": "Installation pilote",
    "Basin clean. Water came back from the main sewer (surcharged downstream): reported to engineering":
        "Puisard propre. L'eau revenait de l'égout principal (en charge en aval) : signalé à l'ingénierie",
    "Battery connector had come loose: re-seated, sensor reporting":
        "Le connecteur de la pile s'était détaché : rebranché, le capteur transmet",
    "Emergency: street flooding. Slow-down signs placed (car wakes were pushing water at doorways)":
        "Urgence : rue inondée. Panneaux « Ralentir » installés (les voitures poussaient l'eau vers les portes)",
    "leaves at the trap lip": "feuilles au rebord de la cloche",
}


def date(m):
    """'Nov 17' -> '17 nov.'"""
    mon, d = m.split()
    return f"{d} {MONTHS.get(mon, mon)}"


def dur(text):
    """'1 h 14 min', '21 min', '3 days', 'a while' -> French (h and min are the same)."""
    return re.sub(r"(\d+) days?$", r"\1 jours", text.replace("a while", "un moment"))


def dec(x):
    return x.replace(".", ",")


def lower_first(s):
    return s[:1].lower() + s[1:]


def upper_first(s):
    return s[:1].upper() + s[1:]


def describe(text):
    """weather.describe(): '29 mm expected in the next 12 h · max 12 mm/h · starts Tue 18:00'."""
    text = text.lstrip("🌧️☀️ ").strip()
    m = re.fullmatch(r"(\d+) mm expected in the next (\d+) h · max (\d+) mm/h(?: · starts (\w{3}) (\d\d:\d\d))?", text)
    if m:
        when = f" · début {DAYS.get(m[4], m[4])} {m[5]}" if m[4] else ""
        return f"{m[1]} mm prévus dans les {m[2]} prochaines heures · max {m[3]} mm/h{when}"
    m = re.fullmatch(r"No significant rain expected in the next (\d+) h", text)
    if m:
        return f"Aucune pluie importante prévue dans les {m[1]} prochaines heures"
    return {"Forecast unavailable (no internet connection)": "Prévision indisponible (pas de connexion internet)"}.get(text, text)


DRAIN = [(r"drained right away", lambda m: "vidé tout de suite"),
         (r"drained in (.+)", lambda m: f"vidé en {dur(m[1])}"),
         (r"still draining", lambda m: "se vide encore"),
         (r"still not drained after (.+)", lambda m: f"toujours pas vidé après {dur(m[1])}")]


def drain(text):
    for pat, f in DRAIN:
        m = re.fullmatch(pat, text)
        if m:
            return f(m)
    return text


def height(text):
    """The second half of a basin's water text."""
    m = re.fullmatch(r"(\d+) cm above the outlet", text)
    if m:
        return f"{m[1]} cm au-dessus du radier"
    return {"outlet depth not learned yet": "profondeur du radier pas encore apprise", "sump emptied": "puisard vidé",
            "at the outlet (resting level)": "au radier (niveau de repos)"}.get(text, text)


PATTERNS = [
    # forecasts and predictions
    (r"Forecast (\d+) mm/h(?: \((\w{3}) (\d\d:\d\d)\))?: water expected to rise to about (\d+) cm above the outlet "
     r"\(backing up at (\d+) cm\)(?:, drains ([\d.]+)x slower than when clean)?\.",
     lambda m: (f"Prévision {m[1]} mm/h" + (f" ({DAYS.get(m[2], m[2])} {m[3]})" if m[2] else "")
                + f" : l'eau devrait monter à environ {m[4]} cm au-dessus du radier (refoulement à {m[5]} cm)"
                + (f", se vide {dec(m[6])} fois plus lentement que propre" if m[6] else "") + ".")),
    (r"Dry forecast \(wettest hour ([\d.]+) mm/h\)\.", lambda m: f"Prévision sèche (heure la plus pluvieuse : {dec(m[1])} mm/h)."),
    (r"Clean before the storm: (.+)", lambda m: f"Nettoyer avant l'orage : {describe(m[1])}"),
    # time
    (r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\w{3}) (\d+)", lambda m: f"{DAYS[m[1]]} {m[3]} {MONTHS.get(m[2], m[2])}"),
    (r"Last reading (.+) ago", lambda m: f"Dernière lecture il y a {dur(m[1])}"),
    (r"(\d+) s ago", lambda m: f"il y a {m[1]} s"),
    (r"(.+) ago", lambda m: f"il y a {dur(m[1])}"),
    (r"< 10 min", lambda m: "< 10 min"),
    (r"(.+) \(normal < 10 min\)", lambda m: f"{dur(m[1])} (normal < 10 min)"),
    (r"(DRY|WATCH|STORM) · every (.+)", lambda m: f"{EXACT[m[1]]} · toutes les {m[2]}"),
    # a basin's facts, water and drainage
    (r"ø(\d+) mm · outlet ([\d.]+) m below the street( \(measured by the sensor\))?",
     lambda m: f"ø{m[1]} mm · radier à {dec(m[2])} m sous la rue" + (" (mesuré par le capteur)" if m[3] else "")),
    (r"ø(\d+) mm · (.+)", lambda m: f"ø{m[1]} mm · {tr(m[2])}"),
    (r"needs a dry, steady day \((\d+) of (\d+) h so far\)",
     lambda m: f"besoin d'une journée sèche et stable ({m[1]} h sur {m[2]} jusqu'ici)"),
    (r"resting water is (\d+) cm (lower|higher) than expected \(sump not refilled since cleaning, or bracket at another height\)",
     lambda m: f"l'eau au repos est {m[1]} cm plus {'basse' if m[2] == 'lower' else 'haute'} que prévu "
               "(puisard pas encore rempli depuis le nettoyage, ou support à une autre hauteur)"),
    (r"Flooding: water backing up, (≤ )?([\d.]+) m below the street",
     lambda m: f"Inondation : l'eau refoule, {m[1] or ''}{dec(m[2])} m sous la rue"),
    (r"Maintenance needed: (.+) \((.+)\)", lambda m: f"Entretien requis : {lower_first(tr(m[1]))} ({tr(m[2])})"),
    (r"Water surface (≤ )?([\d.]+) m below the street( \(above the sensor's range\))? · (.+)",
     lambda m: f"Surface de l'eau {m[1] or ''}{dec(m[2])} m sous la rue"
               + (" (au-dessus de la plage du capteur)" if m[3] else "") + f" · {height(m[4])}"),
    (r"(~|≤)(\d+)% capacity( · sump filling \(est\. (\d+)%\))?",
     lambda m: f"{m[1]}{m[2]} % de capacité" + (f" · puisard qui se remplit (est. {m[4]} %)" if m[3] else "")),
    (r"Only ~(\d+)% of the runoff gets in", lambda m: f"Seulement ~{m[1]} % du ruissellement entre"),
    (r"Inferred restriction: (~|≤)(\d+)% capacity", lambda m: f"Restriction déduite : {m[1]}{m[2]} % de capacité"),
    # the action banner's rows
    (r"Before the rain starts: (.+)", lambda m: f"Avant le début de la pluie : {lower_first(tr(upper_first(m[1])))}"),
    (r"Battery low \(~(\d+)%\): replace it now", lambda m: f"Pile faible (~{m[1]} %) : la remplacer maintenant"),
    (r"Battery low \(~(\d+)%\): replace it on the next visit",
     lambda m: f"Pile faible (~{m[1]} %) : la remplacer à la prochaine visite"),
    (r"Sensor silent for (.+)", lambda m: f"Capteur muet depuis {dur(m[1])}"),
    (r"Debris in the trap or a partial pipe restriction \(sump only ~(\d+)% full, estimated\)",
     lambda m: f"Débris dans la cloche ou restriction partielle de la conduite (puisard rempli à seulement ~{m[1]} %, estimé)"),
    (r"Sediment likely reaching the trap lip \(sump ~(\d+)% full, estimated\) or a partial pipe restriction",
     lambda m: f"Sédiments qui atteignent probablement le rebord de la cloche (puisard rempli à ~{m[1]} %, estimé) "
               "ou restriction partielle de la conduite"),
    (r"Sump filling up: ~(\d+)% full \(estimated\)", lambda m: f"Puisard qui se remplit : ~{m[1]} % (estimé)"),
    (r"Filled to the top of the sensor range in the (\w{3} \d+) rain \((\d+) mm\)(, took (.+) to drain \(< 10 min when clean\))?",
     lambda m: f"Rempli jusqu'au haut de la plage du capteur lors de la pluie du {date(m[1])} ({m[2]} mm)"
               + (f", s'est vidé en {dur(m[4])} (< 10 min quand propre)" if m[3] else "")),
    (r"Rose (\d+) cm in the (\w{3} \d+) rain \(≈(\d+) cm when clean\)(, took (.+) to drain \(< 10 min when clean\))?",
     lambda m: f"Monté de {m[1]} cm lors de la pluie du {date(m[2])} (≈{m[3]} cm quand propre)"
               + (f", s'est vidé en {dur(m[5])} (< 10 min quand propre)" if m[4] else "")),
    (r"Water barely got in during the (\w{3} \d+) rain \(rose (\d+) cm, ≈(\d+) cm normally\)",
     lambda m: f"L'eau est à peine entrée lors de la pluie du {date(m[1])} (montée de {m[2]} cm, ≈{m[3]} cm normalement)"),
    # storms
    (r"Rose only (\d+) cm in a big rain \(clean: ~(\d+) cm\)",
     lambda m: f"Monté de seulement {m[1]} cm lors d'une grosse pluie (propre : ~{m[2]} cm)"),
    (r"Reached the top of the sensor range, (.+)", lambda m: f"A atteint le haut de la plage du capteur, {drain(m[1])}"),
    (r"Rose (\d+) cm, (.+)", lambda m: f"Monté de {m[1]} cm, {drain(m[2])}"),
    # the run and the log
    (r"Pre-storm run · stop (\d+) of (\d+) · arrive (\d\d:\d\d)(?: · (.*))?",
     lambda m: f"Tournée préventive · arrêt {m[1]} de {m[2]} · arrivée {m[3]}" + (f" · {tr(m[4])}" if m[4] else "")),
    (r"(\d+) mm of sediment removed(?:; (.*))?",
     lambda m: f"{m[1]} mm de sédiments retirés" + (f"; {tr(m[2])}" if m[2] else "")),
    (r"(.+) at (\d\d:\d\d)", lambda m: f"{tr(m[1])} à {m[2]}"),
    (r"(.+)\. Backfilling into the subdrains / road base",
     lambda m: f"{tr(m[1])}. Refoulement dans les drains / la fondation de la chaussée"),
]
PATTERNS = [(re.compile(p), f) for p, f in PATTERNS]


def tr(text):
    if not isinstance(text, str) or not text:
        return text
    if text in EXACT:
        return EXACT[text]
    for pat, f in PATTERNS:
        m = pat.fullmatch(text)
        if m:
            return f(m)
    return text


def translate(obj, key=None):
    """Translate the display text in a page's answer (dicts and lists, walked recursively)."""
    if isinstance(obj, dict):
        return {k: translate(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        if key == "rows":                                    # the banner's [label, text] pairs
            return [[tr(x) for x in row] if isinstance(row, (list, tuple)) else translate(row, key) for row in obj]
        return [translate(v, key) for v in obj]
    if isinstance(obj, tuple):
        return translate(list(obj), key)
    if isinstance(obj, str) and key in DISPLAY:
        return tr(obj)
    return obj
