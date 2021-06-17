# -*- coding: utf-8 -*-

"""
福岡市水道局の月額請求情報を取得
検針日は偶数月の上旬 (4-7日くらい)

カラーパレットはこのページで指定
https://www.materialui.co/colors
"""

from bs4 import BeautifulSoup
# import urllib.request as req
import requests
# from urllib.error import HTTPError

import psycopg2

import datetime
from dateutil.relativedelta import relativedelta
import re
import os

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import japanize_matplotlib


def get_info(year, month):
    url_login = 'https://ryokin.suido.city.fukuoka.lg.jp/fws/internal/login'

    # ID = ''
    # PASSWORD = ''
    id = os.environ['id_water']  # 環境変数から ID を読み込み
    password = os.environ['password_water']  # 環境変数から Password を読み込み

    session = requests.session()

    # token の取得
    res = session.get(url_login)
    soup = BeautifulSoup(res.text, 'html.parser')
    _csrf = soup.find(attrs={'name': '_csrf'}).get('value')
    login = soup.find(attrs={'name': 'login'}).get('value')

    # リクエストパラメータ
    data_login = {
        'loginId': id,
        'password': password,
        '_csrf': _csrf,
        'login': login
    }

    # ログインする
    url_authente = 'https://ryokin.suido.city.fukuoka.lg.jp/fws/internal/authente'
    session.post(url_authente, data=data_login)

    # ホームページに移行
    url_bills = 'https://ryokin.suido.city.fukuoka.lg.jp/fws/internal/dp0009/'
    res = session.get(url_bills)
    soup = BeautifulSoup(res.text, 'html.parser')

    # ---

    # 和暦計算
    gengo, year_wareki = calc_seireki_to_wareki(year=year, month=month)
    # 全角変換
    ## https://qiita.com/YuukiMiyoshi/items/6ce77bf402a29a99f1bf
    year_wareki_fullwidth = str(year_wareki).translate(str.maketrans({chr(0x0021 + i): chr(0xFF01 + i)
                                                                      for i in range(94)}))
    month_fullwidth = str(month).translate(str.maketrans({chr(0x0021 + i): chr(0xFF01 + i)
                                                          for i in range(94)}))

    # 更新チェック
    ## 対象年月のデータが出ているか確認 -> 出ていなかったら終了
    ## wareki, month に関しては2桁分のスペースが取られている、1桁の数字に関しては十の位が'　'で穴埋めされるので注意
    ## '1月' -> '　１月', '12月' -> '１２月'
    check_wareki = soup.find(name='span',
                             text='{gengo}{wareki}年{month}月検針分'.format(gengo=gengo,
                                                                       wareki=('　' + year_wareki_fullwidth)[-2:],
                                                                       month=('　' + month_fullwidth)[-2:]))

    if check_wareki is None:
        print('まだ{year}年{month}月のデータは出ていません'.format(year=year, month=month))
        exit()

    # 対象の年月における html を取得
    soup = check_wareki.parent.parent

    # 必要な項目の取得
    # 今回検針日
    this_date = soup.find(name='th', text='検針日')
    this_date = this_date.next_sibling.next_sibling.string
    pattern = '([A-Z]+)' + '([0-9])+' + '/' + '([0-9]+)' + '/' + '([0-9]+)'
    search = re.search(pattern=pattern, string=this_date)
    pre_gengo = search.group(1)
    this_wareki = int(search.group(2))
    this_month = int(search.group(3))
    this_day = int(search.group(4))
    ## 和暦から西暦に変換
    this_year = calc_wareki_to_seireki(pre_gengo=pre_gengo, wareki=this_wareki)
    this_date = datetime.date(this_year, this_month, this_day)
    # 使用水量
    amount = soup.find(lambda x: '水道使用量(m3)' in x.text and x.name == 'th')
    amount = amount.next_sibling.next_sibling.string
    amount = int(amount)  # 型変換
    # 合計金額 (水道料金 + 下水道使用料)
    fee_total_get = soup.find(name='th', text='合計金額(円)')
    fee_total_get = fee_total_get.next_sibling.next_sibling.string
    fee_total_get = int(fee_total_get.replace(',', ''))  # 型変換

    # その他, 福岡市水道局の場合は固定値
    # 口径
    pipe_size = 13
    # 用途
    usage = '家事用'
    # 下水道使用状況
    sewerage = '有'
    # 下水道使用料算定根拠
    sewerage_basis = '水道使用量'
    # 水道基本料金
    ## メーターの口径が13mmなら1700円
    fee_basic_water = 1700
    # 水道従量料金単価
    ## メーターの口径が25mm以下で使用水量が20m3以下なら17円
    fee_unit_according_water = 17
    # 消費税率
    rate_tax = 0.1
    # 下水道基本使用料
    ## 一般汚水の場合、汚水排出量に関係なく1520円
    fee_basic_sewerage = 1520
    # 利用水道会社
    name_company = '福岡市水道局 東営業所'
    # お客様番号, ID と一緒
    # code_customer = '30082907004'
    # 使用住居
    name_house = 'ハイネタウン箱崎 #601'

    dict_info = {
        'this_date': this_date,
        'amount': amount,
        'fee_total_get': fee_total_get,
        'pipe_size': pipe_size,
        'usage': usage,
        'sewerage': sewerage,
        'sewerage_basis': sewerage_basis,
        'fee_basic_water': fee_basic_water,
        'fee_unit_according_water': fee_unit_according_water,
        'rate_tax': rate_tax,
        'fee_basic_sewerage': fee_basic_sewerage,
        'name_company': name_company,
        'code_customer': id,
        'name_house': name_house
    }

    return dict_info


def calc_seireki_to_wareki(year, month):
    date_target = datetime.date(year, month, 1)

    dict_wareki = {'令和': [datetime.date(2019, 5, 1), datetime.date(2099, 12, 31)]}

    for k, v in dict_wareki.items():
        date_start = v[0]
        date_end = v[1]
        if date_start <= date_target <= date_end:
            gengo = k
            year_wareki = year - date_start.year + 1

    return gengo, year_wareki


def calc_wareki_to_seireki(pre_gengo, wareki):
    dict_wareki = {'令和': [datetime.date(2019, 5, 1), datetime.date(2099, 12, 31)]}

    if pre_gengo == 'R':
        date_start = dict_wareki['令和'][0]
        year_start = date_start.year
        year = year_start + wareki - 1
    else:
        raise Exception

    return year


def calc_data(dict_info):
    """
    取得データから水道料金等を計算
    """
    amount = dict_info['amount']  # 水道使用量(m3)
    fee_basic_water = dict_info['fee_basic_water']  # 水道基本料金
    fee_unit_according_water = dict_info['fee_unit_according_water']  # 水道従量料金単価
    rate_tax = dict_info['rate_tax']  # 消費税率
    fee_basic_sewerage = dict_info['fee_basic_sewerage']  # 下水道基本使用料
    fee_total_get = dict_info['fee_total_get']  # 取得した合計金額
    year = dict_info['year']
    month = dict_info['month']

    # 水道従量料金
    fee_according_water = amount * fee_unit_according_water
    # 水道料金
    fee_total_water = int((fee_basic_water + fee_according_water) * (1 + rate_tax))  # 小数点以下切り捨て
    # 水道料金 うち消費税
    tax_water = int((fee_basic_water + fee_according_water) * rate_tax)  # 小数点以下切り捨て
    # 下水道使用料金, 20m3以下なら従量料金単価は13円
    fee_total_sewerage = int((fee_basic_sewerage + amount * 13) * (1 + rate_tax))  # 小数点以下切り捨て
    # 下水道使用料金 うち消費税
    tax_sewerage = int((fee_basic_sewerage + amount * 13) * rate_tax)  # 小数点以下切り捨て
    # 合計金額
    fee_total_calc = fee_total_water + fee_total_sewerage
    # 合計金額 うち消費税
    tax = int(fee_total_calc * rate_tax)
    # 誤差
    diff = fee_total_get - fee_total_calc

    # 前回検針日取得
    str_query = """
        SELECT 
            this_date
        FROM
            fee_water
        WHERE
            year = {year}
            AND month = {month}
        """
    date_temp = datetime.date(year, month, 1)
    momth_before = (date_temp - relativedelta(months=2)).month
    year_before = (date_temp - relativedelta(months=2)).year
    str_query = str_query.format(year=year_before, month=momth_before)
    # Execute
    cur.execute(str_query)
    res = cur.fetchall()
    if len(res) != 0:
        prev_date = res[0][0]
        dict_info['prev_date'] = prev_date
    else:
        pass

    # 要素を追加
    # l = [fee_total_water, tax_water, fee_total_sewerage, tax_sewerage, fee_total_calc, tax, diff]
    dict_info['fee_according_water'] = fee_according_water
    dict_info['fee_total_water'] = fee_total_water
    dict_info['tax_water'] = tax_water
    dict_info['fee_total_sewerage'] = fee_total_sewerage
    dict_info['tax_sewerage'] = tax_sewerage
    dict_info['fee_total_calc'] = fee_total_calc
    dict_info['tax'] = tax
    dict_info['diff'] = diff

    return dict_info


def connect_database():
    # Settings
    host = os.environ['database_host']
    port = os.environ['database_port']
    user = os.environ['database_user']
    name_db = os.environ['database_name']
    password = os.environ['database_password']

    # Connect
    str_dsn = 'host={host} port={port} dbname={dbname} user={user} password={password}'
    str_dsn = str_dsn.format(host=host, port=port, dbname=name_db, user=user, password=password)
    conn = psycopg2.connect(str_dsn)

    # excexute sql
    cur = conn.cursor()
    # cur.execute('SELECT * FROM fee_gas;')
    # res = cur.fetchall()
    # print(res)

    return conn, cur


def check_update(year, month, cur):
    str_query = """
    SELECT 
        *
    FROM
        fee_water
    WHERE
        year = {year}
        AND month = {month}
    """
    str_query = str_query.format(year=year, month=month)

    # Execute
    cur.execute(str_query)
    res = cur.fetchall()
    if len(res) > 0:
        # 既に対象の年月が書き込まれていたら終了
        print('もう書き込まれてんで')
        exit()
    else:
        return 0


def insert_data(conn, cur, dict_info):
    str_query = """
    INSERT INTO fee_water ({name_columns}) VALUES ({name_values});
    """
    list_columns = list(dict_info.keys())
    list_values_root = list(dict_info.values())
    list_values = []
    # 型に応じて、表記方法を変える
    for i in list_values_root:
        if type(i) == datetime.date:
            list_values.append('DATE' + '\'' + str(i) + '\'')
        elif type(i) == str:
            list_values.append('\'' + i + '\'')  # 文字列であることを示すシングルクォーテーションを入れる
        else:
            list_values.append(str(i))
    str_columns = ', '.join(list_columns)
    str_values = ', '.join(list_values)
    str_query = str_query.format(name_columns=str_columns, name_values=str_values)

    print(str_query)

    # Execute
    cur.execute(str_query)
    conn.commit()
    print(cur.statusmessage)


def draw_graph(year, month, cur):
    # 2年前を取得
    date_temp = datetime.date(year, month, 1)
    month_before = (date_temp - relativedelta(months=23)).month
    year_before = (date_temp - relativedelta(months=23)).year
    # print(year_before, month_before)

    # 過去2年間分を取得
    str_query = """
    SELECT 
        year, month, amount, fee_total_get
    FROM
        fee_water
    WHERE
        -- 23ヶ月前までのデータを取得
        TO_DATE(CAST(year AS CHARACTER VARYING) || LPAD(CAST(month AS CHARACTER VARYING), 2, '0') || '01', 'YYYYMMDD') >= '{year_before}-{month_before}-01'
        AND TO_DATE(CAST(year AS CHARACTER VARYING) || LPAD(CAST(month AS CHARACTER VARYING), 2, '0') || '01', 'YYYYMMDD') <= '{year}-{month}-01'
        AND CAST(month AS SMALLINT) % 2 = 0;
    """
    str_query = str_query.format(year_before=year_before, month_before=month_before, year=year, month=month)

    # Execute
    cur.execute(str_query)
    res = cur.fetchall()

    df_draw = pd.DataFrame(res, columns=['year', 'month', 'amount', 'fee'])
    df_draw = df_draw.sort_values(['year', 'month'])
    df_draw['num_series'] = [i for i in range(6)] * 2  # 最新月をグラフの右に表示させるための機構
    df_draw['num_last'] = ['去年'] * 6 + ['今年'] * 6  # 昨年度のデータは薄く表示させるための機構
    print(df_draw)

    # 描画
    fig, ax1 = plt.subplots(figsize=(20, 10))
    ax2 = ax1.twinx()  # 合計金額
    sns.barplot(data=df_draw, x='num_series', y='amount', hue='num_last', palette=['#BBDEFB', '#2196F3'], ax=ax1)
    sns.lineplot(data=df_draw, x='num_series', y='fee', hue='num_last', palette=['#ffcdd2', '#f44336'], ax=ax2)
    ax1.set_ylim(0, df_draw['amount'].max() + 5)
    ax2.set_ylim(0, df_draw['fee'].max() + 100)
    ## ラベル調整
    ax1.set_title('水道代', fontsize=40)
    ax1.set_ylabel('水道使用量 (㎥)', fontsize=30)
    ax2.set_ylabel('合計金額 (円)', fontsize=30)
    ax1.set_xlabel('月', fontsize=30)
    list_month = list(df_draw.loc[df_draw.index.to_list()[int(-len(df_draw)/2):], 'month'].values)
    list_month = ['{0}月'.format(int(i)) for i in list_month]
    ax1.set_xticklabels(list_month)
    ax1.tick_params(axis='both', labelsize=20)
    ax2.tick_params(axis='y', labelsize=20)
    ## 凡例を削除
    ax1.get_legend().remove()
    ax2.get_legend().remove()
    # g._legend.remove()
    # plt.show()
    plt.savefig('output.jpg')

    return df_draw


def send_message(df_draw, year, month):
    # 必要な値を算出
    df_temp = df_draw[df_draw['month'] == month]
    [amount_before, amount] = df_temp['amount'].to_list()
    amount_diff = amount - amount_before
    amount = '{:,}'.format(amount)  # カンマ区切りにする
    if amount_diff >= 0:
        amount_diff = '{:,}'.format(amount_diff)  # カンマ区切りにする
        amount_diff = '+' + str(amount_diff)
    else:
        amount_diff = '{:,}'.format(amount_diff)  # カンマ区切りにする
    [fee_before, fee] = df_temp['fee'].to_list()
    fee_diff = fee - fee_before
    fee = '{:,}'.format(fee)  # カンマ区切りにする
    if fee_diff >= 0:
        fee_diff = '{:,}'.format(fee_diff)  # カンマ区切りにする
        fee_diff = '+' + str(fee_diff)
    else:
        fee_diff = '{:,}'.format(fee_diff)  # カンマ区切りにする
    message = ('{year}年{month}月 - 水道代が確定！'
               + '\n使用量: {amount}㎥ (前年比: {amount_diff}㎥)'
               + '\n合計金額: {fee}円 (前年比: {fee_diff}円)')
    message = message.format(year=year, month=month,
                             amount=amount, amount_diff=amount_diff, fee=fee, fee_diff=fee_diff)

    token = 'xoxb-1082152242931-2036134552961-7FwhggqkYLFuTmJJ50mAgTZl'
    token = os.environ['slack_token']
    channel_id = 'C024R5EAH55'  # チャンネル名: notice-lifeline-cost

    files = {'file': open('output.jpg', 'rb')}
    param = {
        'token': token,
        'channels': channel_id,
        'filename': 'filename',
        'initial_comment': message,
        'title': 'water fee - {year}.{month}.jpg'.format(year=year, month=month)
    }

    requests.post(url='https://slack.com/api/files.upload', data=param, files=files)

    return 0


if __name__ == '__main__':
    today = datetime.date.today()
    year = today.year
    month = today.month

    # 偶数月でなかったら終了
    if month % 2 != 0:
        print('偶数月を指定してね')
        exit()

    # Connect Database
    conn, cur = connect_database()

    # df_draw = draw_graph(year=year, month=month, cur=cur)
    # send_message(df_draw=df_draw, year=year, month=month)
    # exit()

    # 対象の年月が既に Database に書き込まれているか確認
    check_update(year=year, month=month, cur=cur)

    dict_info = get_info(year=year, month=month)

    # 必要なデータを揃える
    dict_info['year'] = year
    dict_info['month'] = month
    dict_info = calc_data(dict_info=dict_info)

    # print(dict_info)

    # 書き込み
    insert_data(conn=conn, cur=cur, dict_info=dict_info)

    # グラフを描画
    df_draw = draw_graph(year=year, month=month, cur=cur)

    # メッセージを送信
    send_message(df_draw=df_draw, year=year, month=month)




