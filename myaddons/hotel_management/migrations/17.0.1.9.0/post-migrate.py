# Descriptions des types de chambre affichées sur la page d'accueil du site :
# on remplace les textes d'origine (très courts) uniquement s'ils n'ont pas été modifiés.
DESCRIPTIONS = {
    'room_type_single': (
        "Dortoir mixte, location au lit.",
        "Un lit confortable dans un dortoir partagé et convivial : "
        "la formule idéale pour voyager malin."),
    'room_type_suite': (
        "Dortoir réservé aux femmes, location au lit.",
        "Un dortoir réservé aux femmes, calme et rassurant, "
        "pour voyager seule en toute sérénité."),
    'room_type_double': (
        "Chambre privée pour 1 à 2 personnes.",
        "Une chambre rien que pour vous, au calme, "
        "pour se reposer en toute tranquillité."),
    'room_type_family': (
        "Chambre familiale, louable au lit.",
        "Une grande chambre pour partager le séjour en famille, "
        "avec un lit pour chacun."),
}


def migrate(cr, version):
    for xmlid, (old, new) in DESCRIPTIONS.items():
        cr.execute("""
            UPDATE hotel_room_type t
               SET description = %s
              FROM ir_model_data d
             WHERE d.module = 'hotel_management'
               AND d.name = %s
               AND d.model = 'hotel.room.type'
               AND d.res_id = t.id
               AND t.description = %s
        """, (new, xmlid, old))
