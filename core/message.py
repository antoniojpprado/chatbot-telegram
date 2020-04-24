import logging.config
import numpy
import os

from psycopg2.extras import NamedTupleCursor
import telegram
import time
from bot_webhook.settings import TOKEN
from core.models import Contact, Interaction
from django.db import connections
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from matplotlib import pyplot
from matplotlib.font_manager import FontProperties
import matplotlib.patches as mpatches
from pythonjsonlogger import jsonlogger
from tempfile import NamedTemporaryFile

bot = telegram.Bot(token=TOKEN)

# Habilitar logging:
logging.config.fileConfig('logging.ini', disable_existing_loggers=False)
logger = logging.getLogger(__name__)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

def proccess(json_telegram):
    """
    Recebe a mensagem, enviada pela view, e solicita a autorização do contato,
    para então interagir com ele, conforme for.
    :param json_telegram: Mensagem recebida
    """
    msg = msg_handler(json_telegram)
    try:
        starttime = time.time()
        # Y = (10 / 0)
        if 'callback' in msg:
            if msg['option'] == 'graph':
                callback_graph(msg)
                options_callback(msg)

            else:
                if msg['option'] == 'spread':
                    callback_table(msg)
                options_start(msg, msg_text=False)

        else:
            if login(msg):
                options_start(msg)

            else:
                msg_login(msg)

        endtime = time.time()
        duration = endtime - starttime
        logger.info("Processando mensagem:", extra={"run_duration": duration})

    except Exception as error:
        logger.exception(error)


def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    """
    Constrói um menu com os botões das opções para o contato.
    :param buttons: Os botões que compõe o menu.
    :param n_cols: Quantidade de colunas que deverá conter o menu.
    :param header_buttons: Cabeçalho dos botões.
    :param footer_buttons: Rodabé dos botões.
    :return: O menu.
    """
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, [header_buttons])
    if footer_buttons:
        menu.append([footer_buttons])
    return menu


def callback_graph(msg):
    """
    Apresentar o gráfico de barras, relativo a opção escolhida.
    :param msg: Mensagem recebida
    """
    try:
        # Obtem o código da SQL query a ser consultada, na base de dados, e a executa:
        interaction = Interaction.objects.get(input=msg['callback'])
        code = interaction.code
        dic = get_data(code)
        # Constrói a lista de dados para os eixos x e y:
        xaxis = []
        yaxis_a = []
        yaxis_b = []
        for row in dic:
            xaxis.append('{:02d}:{:02d}'.format(row['time'].hour, row['time'].minute))
            yaxis_a.append(row['point'])
            yaxis_b.append(row['out_point'])
        # Construir o gráfico de barras:
        exec(interaction.graph_labels, globals())  # Declarar title, xlabel e ylabel.
        xordem = numpy.arange(len(xaxis))
        if interaction.type == 'Column':
            pyplot.bar(xordem, yaxis_a, label='Ponta', color='red', alpha=0.7)
            pyplot.bar(xordem, yaxis_b, label='Fora Ponta', color='royalblue', alpha=0.7, bottom=yaxis_a)
        else:
            raise ValueError('Interaction Type nao previsto: {}'.format(interaction.type))
        pyplot.xticks(xordem, xaxis)
        pyplot.grid(color='#95a5a6', linestyle='--', linewidth=2, axis='y', alpha=0.7)
        # Criar as legendas:
        ## Logomarca
        logo = pyplot.imread('logo_equiplex.png')
        pyplot.figimage(logo, 30, 433)
        ## Título
        pyplot.title(title, fontsize=14)
        pyplot.figtext(0.9, 0.9, dic[0]['equipment_name'], horizontalalignment='right', fontsize=8)
        ## Valores
        pyplot.ylabel(ylabel)
        ## Rodapé
        pyplot.xlabel(xlabel)
        pyplot.xticks(rotation=45, fontsize=6)
        pyplot.figtext(0.89, 0.01, 'Gerado em 10/01/1980 12:00', horizontalalignment='right', fontsize=6)
        ## Barras
        pyplot.legend(fontsize=6)
        # Apresentar o gráfico:
        msg_photo(msg)

    except ValueError as error:
        logger.exception(error)
        raise


def callback_table(msg):
    """
    Apresentar tabela com os dados, relativo a opção escolhida.
    :param msg: Mensagem recebida
    """
    # Obter o código da SQL query a ser consultada, na base de dados, e a executa:
    interaction = Interaction.objects.get(input=msg['callback'])
    code = interaction.code
    dic = get_data(code)
    # Construir a lista de dados:
    pyplot.axis('off')
    table_values = []
    count = 0
    for row in dic:
        pyplot.title(label='Consumo', fontsize=14)
        if count == 24:
            # Construir e apresentar a tabela:
            make_table(table_values)
            msg_photo(msg)
            # Iniciar nova lista de dados:
            table_values = []
            count = 0
        table_values.append(['{:02d}:{:02d}'.format(row[0].hour, row[0].minute), row[1]])
        count += 1


def get_data(sql):
    cur = connections['app'].cursor()
    cur.execute(sql)
    data = cur.fetchall()

    fieldnames = [name[0] for name in cur.description]
    result = []
    for row in data:
        rowset = []
        for field in zip(fieldnames, row):
            rowset.append(field)
        result.append(dict(rowset))

    cur.close()

    return result


def get_dataSAVE(sql):
    cur = connections['app'].cursor()
    cur.execute(sql)
    data = cur.fetchall()
    cur.close()
    return data


def login(msg):
    """
    Verifica se o usuário consta na base de dados do App Care e interage com o contato.
    Também registra na base do bot, os dados do novo contato do bot, caso ainda não exista.
    :param msg: Mensagem recebida
    :return: Falso ou verdadeiro, para a autorização do contato.
    """
    try:
        # Verifica se o usuário existe na base da dados do Bot
        contact = Contact.objects.get(user_id=msg['user_id'])

    except Contact.DoesNotExist:
        try:
            # Verifica se o contato é cadastrado na base do App Care.
            if user_app(msg['phone_number']):
                # Salva o contato na base de dados do Bot.
                Contact(
                    user_id=msg['user_id'],
                    first_name=msg['first_name'],
                    last_name=msg['last_name'],
                    phone_number=msg['phone_number']
                ).save()

            else:
                bot.send_message(
                    text='Olá {0} {1}!\n\n'
                         'Não te localizei como um usuário registrado.\n\n'
                         'Solicite o cadastro no App Care e retorne para que eu possa te atender.\n\n'
                         'Obrigado pelo contato.'.format(msg['first_name'], msg['last_name']),
                    chat_id=msg['user_id'])
                return False

        except BaseException:
            return False

    return True


def make_table(table_values):
    """
    Construir uma tabela.
    :param table_values: Lista de valores que compõe a tabela.
    :return: A tabela criada.
    """
    # Construir a tabela:
    col_labels = ['Hora', 'Valor']
    table = pyplot.table(cellText=table_values,
                         colWidths=[0.1] * 3,
                         colLabels=col_labels,
                         loc='center')
    table.auto_set_font_size(False)
    table.scale(4, 4)
    n_rows = len(table_values)
    # Centralizar primeira coluna:
    cells = table.properties()['celld']
    for i in range(n_rows+1):
        cells[i, 0]._loc = 'center'
    # Bold na primeira linha:
    cells[0, 0].set_text_props(fontproperties=FontProperties(weight='bold'))
    cells[0, 1].set_text_props(fontproperties=FontProperties(weight='bold'))
    # Tamanho das fontes:
    table.set_fontsize(24)
    # Cores da tabela:
    table[(0, 0)].set_facecolor('#c5d4e6')
    table[(0, 1)].set_facecolor('#c5d4e6')
    color = 'white'
    for row in range(n_rows):
        table[(row+1, 0)].set_facecolor(color)   # A primeira linha, cabeçalho, tem cor específica.
        table[(row+1, 1)].set_facecolor(color)
        color = '#e2e9f2' if color == 'white' else 'white'
    return table


def msg_handler(json_telegram):
    """
    Extrai os dados que serão manipulados, da mensagem enviada pelo Telegram.
    :param json_telegram: Mensagem recebida.
    :return: Dicionário msg com os dados a serem manipulados.
    """
    if 'callback_query' in json_telegram:
        user_id = json_telegram['callback_query']['from']['id']
        first_name = json_telegram['callback_query']['from']['first_name']
        last_name = json_telegram['callback_query']['from']['last_name']
        callback = json_telegram['callback_query']['data']
        if callback == 'start':
            option = callback

        else:
            if 'Graph' in callback:
                option = 'graph'
                callback = callback.replace('Graph ', '')

            else:
                option = 'spread'
                callback = callback.replace('Spread ', '')

        msg = {'user_id': user_id,
               'first_name': first_name,
               'last_name': last_name,
               'callback': callback,
               'option': option}

    else:
        user_id = json_telegram['message']['from']['id']
        first_name = json_telegram['message']['from']['first_name']
        last_name = json_telegram['message']['from']['last_name']
        msg = {'user_id': user_id, 'first_name': first_name, 'last_name': last_name}

        if 'contact' in json_telegram['message']:
            msg['phone_number'] = json_telegram['message']['contact']['phone_number']

    return msg


def msg_login(msg):
    """
    Interage com o contato, solicitando os seus dados para autorizar o acesso.
    :param msg: Mensagem do contato
    """
    reply_markup = telegram.ReplyKeyboardMarkup(
        [[telegram.KeyboardButton('Click para Login', request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    bot.sendMessage(msg['user_id'], 'Preciso autorizar seu acesso.', reply_markup=reply_markup)


def msg_photo(msg):
    """
    Enviar a imagem ao Telegram
    :param msg: A mensagem a qual deve ser retornada a imagem
    """
    img = NamedTemporaryFile(delete=False)
    img = img.name
    pyplot.savefig(img, bbox_inches='tight', format='png')
    pyplot.show()
    bot.sendPhoto(chat_id=msg['user_id'], photo=open(img, 'rb'))
    os.unlink(img)


def options_start(msg, msg_text=True):
    """
    Apresenta ao contato, a lista de opções.
    :param msg: Mensagem do contato.
    :param msg_text: Se deve apresentar texto.
    """
    interaction = Interaction.objects.all().values('input').order_by('input')
    interaction = list(interaction)
    button_list = []
    for row in interaction:
        button_list.append(InlineKeyboardButton(row['input'], callback_data='Graph {}'.format(row['input'])))
    reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=2))
    if msg_text:
        text = 'Olá {0} {1}!\nTenho disponível estas informações:'.format(msg['first_name'], msg['last_name'])
    else:
        text = 'Disponível:'
    bot.send_message(text=text, chat_id=msg['user_id'], reply_markup=reply_markup)


def options_callback(msg):
    """
    Apresenta ao contato, a lista de opções.
    :param msg: Mensagem do contato.
    :param msg_text: Se deve apresentar texto.
    """
    button_list_callback = [
        InlineKeyboardButton('Planilha dos Dados', callback_data='Spread {}'.format(msg['callback'])),
        InlineKeyboardButton('Retornar ao início', callback_data='start')
    ]
    reply_markup = InlineKeyboardMarkup(build_menu(button_list_callback, n_cols=2))
    text = 'Também tenho disponível:'
    bot.send_message(text=text, chat_id=msg['user_id'], reply_markup=reply_markup)


def user_app(phone_number):
    """
    Verifica a existência do contato, na base de dados do App Care.
    :param phone_number: Utilizado como identificação do usuário.
    :return: Dados do user.
    """
    cur = connections['app'].cursor()
    sql = "SELECT id FROM accounts_user WHERE phone_number = '{}'".format(phone_number)
    cur.execute(sql)
    user = cur.fetchone()
    cur.close()
    return user
