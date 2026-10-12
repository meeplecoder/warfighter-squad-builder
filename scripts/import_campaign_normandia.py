"""Import PabloSolano's campaign 'Campaña Warfighter 2GM Europa - Desembarco de Normandía'
(campaigns_scenarios/Campana_Warfighter-1.pdf) as a published campaign owned by 'PabloSolano'.

Eight Core Europe MISSION-OBJECTIVE pairs (W-018…W-033) played in order, with optional medal and
rank rules. Text kept in Spanish as written. Re-running replaces the campaign's content.

Usage: python scripts/import_campaign_normandia.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask_login import login_user

from app import create_app, db
from app.models import Campaign, Card, User
from app.campaigns import _parse, _publish_errors, _save

OWNER_USERNAME = 'PabloSolano'
OWNER_EMAIL = 'pablosolano@community.local'
NAME = 'Campaña Warfighter 2GM Europa - Desembarco de Normandía'

INTRO = (
    'Esta campaña usa las reglas de campaña descritas en el manual de instrucciones original. Tan solo se trata '
    'de una serie de parejas MISIÓN-OBJETIVO y un poco de lore histórico para darle cierta profundidad a la campaña.'
)

MEDALS = """Curar 2 heridas cuenta como una baja a términos de cálculo de medallas.

- El soldado que acabe con 5 enemigos en una misión ganará la medalla "Estrella de Bronce".
- El soldado que acabe con 10 enemigos en una misión ganará la medalla "Estrella de Plata".
- El soldado que consiga combatir en al menos 5 misiones ganará la medalla "Cruz al Servicio Distinguido".
- El soldado que consiga combatir en todas las misiones de la campaña ganará la medalla "Medalla de Honor".
- Los soldados que mueran en combate recibirán a título póstumo la medalla "Corazón púrpura"."""

RANKS = """Dependiendo del número de soldados jugadores, los rangos de la misión 1 serán los siguientes, realizándose por sorteo en caso de más de 1 jugador. Además de a términos de roleo, los rangos deberán usarse para desempatar una planificación en la que no haya unanimidad. ¡Así funciona el ejército, hijo!

1 jugador: Soldado Jugador — 1 Sargento · Soldado no Jugador — 1 Cabo · Escuadra — Soldados
2 jugadores: Soldados Jugadores — 1 Sargento, 1 Cabo · Soldado no Jugador — 1 Soldado de 1ª · Escuadra — Soldados
3 o más jugadores: Soldados Jugadores — 1 Sargento, 2 Cabos · Soldados no Jugadores — Soldados · Escuadra — Soldados

Aunque se gasten los puntos de PE, lleva la cuenta de los que has ido ganando (y de los soldados curados, 2 heridas = 1 PE) y mira la tabla los necesarios para ascender. Si un personaje comienza en un cierto rango, ya tiene los puntos necesarios para haber llegado hasta ahí:

Soldado: 0 · Soldado de 1ª: 3 · Cabo: 8 · Sargento: 15
Sargento Mayor: 22 · Teniente 2ª: 35 · Teniente: 50 · Capitán: 75"""

# (mission card, objective card, title, date, briefing, victory, extra debrief note, rewards)
MISSIONS = [
    ('W-018', 'W-030', 'Un día más - Rescate', '6 de junio de 1944, 01:37 h.',
     'El lanzamiento ha sido una catástrofe. Nos hemos desviado de la ZA tanto que no sabemos dónde estamos. Las '
     'primeras horas han sido solamente esconderse y tratar de buscar a otros soldados. He encontrado solamente a unos '
     'pocos, pero hemos visto que los Krauts se llevaban a unos pocos detenidos a una granja. Está muy cerca y '
     'conocemos perfectamente el terreno, ya que llevamos horas vigilándolo. Si los liberamos seremos suficientes para '
     'hacer algo de daño.',
     'El rescate ha ido bien, y tenemos algunos refuerzos. Lo mejor es que hemos pillado una radio alemana y un mapa, '
     'pero hemos hecho demasiado ruido. Tendremos que movernos.',
     None, None),
    ('W-019', 'W-032', 'Casa por casa - Refugios', '6 de junio de 1944, 03:45 h.',
     'Por fin hemos conseguido tomar un respiro y encontrarnos. Estamos a tomar por saco de donde debíamos caer, pero '
     'por lo que hemos escuchado por la radio cerca de la aldea de Maisy. Les tenemos muchas ganas a los Krauts, por '
     'lo que hemos decidido que como no tenemos órdenes directas, vamos a liberar ese pueblo.',
     'Acabamos con el último comesalchichas, y cuando el silencio se hace, algunos de los vecinos salen a darnos las '
     'gracias. Por el poco francés que recuerdo de la Srta Honey, nos dan las gracias y nos dan comida. Esta gente ha '
     'sufrido mucho, pero el final todavía está lejos. No hay nadie de la resistencia por aquí con una radio y se nos '
     'ha roto la que requisamos, por lo que tendremos que pensar nuestro siguiente paso.',
     None, None),
    ('W-021', 'W-027', 'Batida por el páramo - Puesto de observación', '6 de junio de 1944, 08:30 h.',
     'Hemos liberado el pequeño pueblo, pero no tenemos ni un minuto de respiro. Tras aguantar el contraataque alemán, '
     'se han empezado a escuchar bombardeos en la costa. Parece que comienza el desembarco. Los aldeanos nos han dicho '
     'que aquí cerca hay una batería que ha quedado intacta tras los bombardeos y está haciendo estragos en la playa. '
     'Esto no estaba en los planes, pero habrá que echarle una mano a los compañeros de la playa.',
     'La batería ha quedado destrozada, aunque no ha sido fácil. Los barcos de la marina no dejaban de bombardearla '
     'intentando hacer lo mismo, pero apuntan como un escocés borracho yendo a mear. Seguro que además se apuntan el '
     'tanto. No hemos podido acabar con todos los Krauts, pero al menos el desembarco podrá seguir con una '
     'complicación menos.',
     'NOTA HISTÓRICA: Varios barcos se disputan el "honor" de haber sido los responsables de destruir la batería de '
     'Maisy con sus bombardeos, entre ellos, el HMS Hawkins, pero sin pruebas de haber sido ellos. Como la batería fue '
     'tomada el día 9 por los rangers de Point du Hoc (ver misión 7), se ha aprovechado este vacío para meter esta '
     'misión.',
     None),
    ('W-020', 'W-029', 'Trabajo duro - Cazar al tanque', '6 de junio de 1944, 11:50 h.',
     'Íbamos a volver a Maisy tras destrozar la batería, y va a haber que darse prisa. Desde el puesto de observación '
     'hemos visto que un tanque (un jodido Tiger) se aproxima al pueblo. Podría ser una masacre. Hay que parar a ese '
     'tanque cueste lo que cueste. Al menos en el puesto de observación había suministros.',
     'No sé cómo lo hemos hecho pero lo hemos conseguido. Nos hemos cargado un puto Tiger sin ayuda de blindados. Los '
     'lugareños nos han abierto una botella de champán del de verdad y joder, vamos a tomarnos un trago. Aunque '
     'sigamos en combate, nos lo hemos ganado. Johnny no se lo va a creer cuando se lo cuente.',
     None,
     'MOTE: El soldado que acabe con el tanque recibirá el apodo de "Cazatanques". Si lo hace un soldado '
     'individualmente, recibirá una Cruz al Servicio Distinguido automáticamente.'),
    ('W-022', 'W-028', 'Incursión - Almacén de suministros', '7 de junio de 1944, 16:50 h.',
     'Pasamos el resto del día 6 con escaramuzas, y hemos establecido nuestro pequeño HQ en Maisy, en el rumbo de los '
     'rangers. No sabemos cuánto van a tardar, por lo que necesitamos suministros. Esta gente nos ayuda en lo que '
     'puede pero no es necesario. Un chaval que aún no ha debido empezar a afeitarse, pero que es miembro de la '
     'resistencia nos ha contado que unos kilómetros al sur está Cardonville, una ciudad algo más grande, donde hay un '
     'almacén de suministros que podríamos asaltar. Eso sí, tendrá que ser entrar y salir, porque no hay forma de que '
     'nos enfrentemos a una guarnición alemana tan grande. Salimos ahora para asaltarla esta noche.',
     'Creo que en Berlín hemos dejado a un par de alemanes sin despertar. Hemos asaltado el almacén pero ahora nos '
     'persigue medio Cardonville. Hemos conseguido salir de la ciudad, pero creemos que no ha terminado.',
     None, None),
    ('W-023', 'W-033', 'Apoyo limitado - Hay que largarse', '8 de junio de 1944, 05:50 h.',
     'Los alemanes de Cardonville nos siguen los talones. No podemos ir directos a Maisy, para no llevarlos hasta '
     'allí, por lo que esperamos poder despistarlos entre los setos en dirección noreste. Espero no arrepentirme de '
     'haber venido hasta aquí.',
     'Hemos conseguido despistarlos, y tras reagruparnos, volvemos a Maisy con comida, munición y hasta algo de '
     'chocolate. Mañana tocará intentar llegar hasta la costa a ver si nos unimos a los rangers. El desembarco está '
     'yendo bastante más lento de lo que debía, hay que ponerse las pilas.',
     None, None),
    ('W-024', 'W-026', 'Con lo mínimo - Despejar el búnker', '9 de junio de 1944, 05:30 h.',
     'Por fin algo de suerte. Nos hemos encontrado a los rangers de Pointe du Hoc, que planean acabar con lo que '
     'queda de la batería de Maisy. Nos han encargado a nosotros la destrucción del búnker mientras ellos se encargan '
     'de la enfermería desde la que están atrincherados la mayoría de los Krauts. No vamos a decepcionarlos.',
     'El último rubiales ha caído, el búnker está despejado. A lo lejos escuchamos que el tableteo de las MG42 se '
     'silencia, por lo que los rangers han debido tener éxito. La batería de Maisy es historia, probablemente Omaha '
     'esté más tranquila ahora.',
     None, None),
    ('W-025', 'W-031', 'Camino largo - Capturar el puente', '9 de junio de 1944, 16:45 h.',
     'Parece que por fin empezamos a unificar las playas. Los rangers se han dirigido al este para ayudar con la '
     'captura de Avranches, pero nosotros hemos recibido órdenes nuevas (benditas radios). Ponemos rumbo a Carentan, '
     'la próxima gran ciudad a tomar. Tenemos que esperar allí al resto de la 101ª y a la 2ª de blindados, que están '
     'atrapados en Insigny, combatiendo contra francotiradores rezagados. Nuestro trabajo es tomar el puente que cruza '
     'el río Vire y dejarles vía libre hasta Carentan. Luego nos uniremos a ellos.',
     'Aún no sé cómo conseguimos seguir luchando sin desfallecer tras días apenas durmiendo, pero el puente es '
     'nuestro. Hemos aguantado como jabatos y el camino a Carentan está despejado. Con esto, la invasión va a empezar '
     'a tomar forma. Hitler debería empezar a pensar en cambiarse los pañales.',
     'NOTA HISTÓRICA: El 9 de junio de 1944, cuando la 29ª de infantería llegó al puente, los alemanes lo habían '
     'destruido para evitar precisamente esto. El cuerpo de ingenieros tuvo que inventarse una plataforma usando '
     'balsas para construir un puente artificial temporal para cruzarlo.',
     None),
]


def payload():
    def card_id(number, card_type):
        card = Card.query.filter_by(number=number, card_type=card_type).one()
        return card.id

    missions = []
    for i, (mc, oc, title, date, brief, victory, note, rewards) in enumerate(MISSIONS, 1):
        missions.append({
            'key': f'm{i}', 'code': str(i), 'title': title, 'is_entry': i == 1,
            'mission_card_id': card_id(mc, 'Mission'), 'objective_card_id': card_id(oc, 'Objective'),
            'briefing': f'{date}\n\n{brief}',
            'debrief': f'{victory}\n\n{note}' if note else victory,
            'rewards': rewards,
        })
    return {
        'name': NAME,
        'summary': 'Paracaidistas de la 101ª dispersos tras el lanzamiento del Día D: de Maisy a Carentan en ocho '
                   'parejas MISIÓN-OBJETIVO del Core Europa, del 6 al 9 de junio de 1944.',
        'intro': INTRO,
        'nation': 'US', 'theater': 'Europa - Normandía', 'enemy': 'Alemania', 'period': '6-9 de junio de 1944',
        'flow_type': 'linear',
        'settings': {
            'force': {},
            'persistence': {'xp': True, 'wounds': True, 'skills': True, 'gear': False,
                            'soldiers': True, 'casualties': True},
            'rules': [
                {'title': 'Reglas de campaña',
                 'body': 'Se usan las reglas de campaña descritas en el manual de instrucciones original.'},
                {'title': 'Regla opcional: Medallas', 'body': MEDALS},
                {'title': 'Regla opcional: Rangos y ascensos', 'body': RANKS},
            ],
            'outcomes': [{'label': 'Victoria', 'condition': 'Completar las 8 misiones',
                          'epilogue': 'El puente sobre el Vire es nuestro y el camino a Carentan está despejado.'}],
        },
        'missions': missions,
        'links': [],
        'status': 'published',
    }


def main():
    app = create_app()
    with app.test_request_context():
        owner = User.query.filter_by(username=OWNER_USERNAME).first()
        if not owner:
            owner = User(username=OWNER_USERNAME, email=OWNER_EMAIL, password_hash=None, full_name='Pablo Solano')
            db.session.add(owner)
            db.session.flush()
            print(f'Owner user created: {OWNER_USERNAME}')
        login_user(owner)

        fields, settings, missions, links, errors = _parse(payload())
        errors += _publish_errors(fields, settings, missions)
        if errors:
            sys.exit('Cannot import:\n  ' + '\n  '.join(errors))

        c = Campaign.query.filter_by(user_id=owner.id, name=NAME).first()
        if not c:
            c = Campaign(user_id=owner.id, name=NAME, flow_type='linear', status='published')
            db.session.add(c)
            db.session.flush()
        c.status = 'published'
        _save(c, fields, settings, missions, links)
        db.session.commit()
        print(f'Campaign {c.id} imported: {NAME} ({len(missions)} missions, owner {OWNER_USERNAME})')


if __name__ == '__main__':
    main()
