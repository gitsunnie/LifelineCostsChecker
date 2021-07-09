# -*- coding: utf-8 -*-

"""
参考:
https://qiita.com/fake_engineer_00/items/82c3f63ccb6416fd5fca
https://qiita.com/mSpring/items/257adb27d9170da3b372

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
    url_login = 'https://www.symenergy.net/symenergy/login'

    ID = os.environ['id_electricity']  # 環境変数から ID を読み込み
    PASSWORD = os.environ['password_electricity']  # 環境変数から Password を読み込み

    session = requests.session()
    response = session.get(url_login)

    # BeautifulSoupオブジェクト作成(token取得の為)
    bs = BeautifulSoup(response.text, 'html.parser')

    data_login = {  # リクエストパラメータ
        # '_token': '',
        'login_id': ID,
        'password': PASSWORD
    }

    # tokenの取得
    authenticity_token = bs.find(attrs={'name': '_token'}).get('value')

    # 取得した token を post するパラメータに追加
    data_login['_token'] = authenticity_token

    # ログインする
    session.post(url_login, data=data_login)

    url_bills = 'https://www.symenergy.net/symenergy/meter_readings/65153'
    res = session.get(url_bills)
    soup = BeautifulSoup(res.text, 'html.parser')

    # 指定の年月の明細を指定する
    ## 表示されているリンクのリストを取得
    list_bills_link = soup.find_all(name='a', text='ブラウザで表示')
    ## 表示されている年月のリストを取得
    list_ym = [i.parent.next_sibling.next_sibling.string for i in list_bills_link]
    list_ym = [datetime.datetime.strptime(i, '%Y年%m月') for i in list_ym]

    # 更新チェック
    ## 対象年月のデータが出ているか確認 -> 出ていなかったら終了
    if datetime.datetime(year, month, 1, 0, 0) not in list_ym:
        print('まだ{year}年{month}月のデータは出ていません'.format(year=year, month=month))
        exit()

    index = list_ym.index(datetime.datetime(year, month, 1, 0, 0))
    url_bills_target = list_bills_link[index]['href']
    # 0番目の要素が最新の料金明細になる
    # url_bills_latest = list_bills_link[0]['href']
    # print(url_bills_latest)

    # 最新の料金明細ページにアクセス
    res = session.get(url_bills_target)
    soup = BeautifulSoup(res.text, 'html.parser')

    # ---

    # 必要な項目を取得
    # 前回検針日
    ## 「ご使用期間」の初日が前回検針日にあたる
    prev_date = soup.find(name='span', text=re.compile('ご使用期間[^薔]+')).string
    prev_date = re.search(pattern='ご使用期間 ([^薔]+)～([^薔]+)', string=prev_date).group(1)
    # prev_day = int(re.search(pattern='ご使用期間 ([0-9])月([0-9]+)日[^薔]+', string=prev_date).group(1))
    prev_date = datetime.datetime.strptime(prev_date, '%m月%d日')
    # 今回検針日
    this_date = soup.find(name='span', text=re.compile('検針日[^薔]+')).string
    this_date = re.search(pattern='検針日 ([0-9月日]+)', string=this_date).group(1)
    # this_day = int(re.search(pattern='検針日 ([0-9])月([0-9]+)日', string=this_date).group(2))
    this_date = datetime.datetime.strptime(this_date, '%m月%d日')
    if prev_date.month < this_date.month:
        prev_date = datetime.date(year, prev_date.month, prev_date.day)
    else:
        prev_date = datetime.date(year-1, prev_date.month, prev_date.day)
    this_date = datetime.date(year, this_date.month, this_date.day)
    # 使用量
    amount = soup.find(name='span', text='ご使用量')
    amount = amount.next_sibling.next_sibling.string
    amount = re.search(pattern='([0-9]+)\xa0kWh', string=amount).group(1)
    amount = float(amount.replace(',', ''))  # 型変換
    # 燃料費調整単価
    fee_material = soup.find(name='span', text='当月分')
    fee_material = fee_material.next_sibling.next_sibling.string
    fee_material = re.search(pattern='([0-9-.,]+) 円', string=fee_material).group(1)
    fee_material = float(fee_material.replace(',', ''))  # 型変換
    # 基本料金
    fee_basic = soup.find(name='span', text='基本料金')
    fee_basic = fee_basic.next_sibling.next_sibling.string
    fee_basic = re.search(pattern='([0-9-.,]+)円', string=fee_basic).group(1)
    fee_basic = float(fee_basic.replace(',', ''))  # 型変換
    # 再エネ発電賦課金
    fee_renewable_energy = soup.find(name='span', text='再エネ発電賦課金')
    fee_renewable_energy = fee_renewable_energy.next_sibling.next_sibling.string
    fee_renewable_energy = re.search(pattern='([0-9-.,]+)円', string=fee_renewable_energy).group(1)
    fee_renewable_energy = float(fee_renewable_energy.replace(',', ''))  # 型変換
    # 支払方法登録割引 (口座振替割引)
    discount_account = soup.find(name='span', text=re.compile('口座振替割引額|支払方法登録割引'))
    discount_account = discount_account.next_sibling.next_sibling.string
    discount_account = re.search(pattern='([0-9-.,]+)円', string=discount_account).group(1)
    discount_account = float(discount_account.replace(',', ''))  # 型変換
    # 消費税率
    rate_tax = 0.1
    # （うち消費税相当額）
    tax = soup.find(name='span', text='（うち消費税相当額）')
    tax = tax.next_sibling.next_sibling.string
    tax = re.search(pattern='([0-9-.,]+)円', string=tax).group(1)
    tax = float(tax.replace(',', ''))  # 型変換
    # 契約種別
    type_contract = soup.find(name='span', text='ご契約種別')
    type_contract = type_contract.next_sibling.next_sibling.string
    type_contract = str(type_contract)
    # 契約容量
    type_amount = soup.find(name='span', text='ご契約')
    type_amount = type_amount.next_sibling.next_sibling.string
    type_amount = int(float(re.search(pattern='([0-9.]+) A', string=type_amount).group(1)))
    # 請求料金
    fee_total_get = soup.find(name='span', text='請求予定金額')
    fee_total_get = fee_total_get.next_sibling.next_sibling.string
    fee_total_get = re.search(pattern='([0-9-.,]+)円', string=fee_total_get).group(1)
    fee_total_get = int(fee_total_get.replace(',', ''))  # 型変換
    # 電力料金単価 (1段階目)
    ## Sym Energy の場合は 17.26
    fee_unit_according_first = 17.26
    # 電力料金単価 (1段階目)
    ## Sym Energy の場合は 21.39
    fee_unit_according_second = 21.39
    # 電力料金単価 (1段階目)
    ## Sym Energy の場合は 23.43
    fee_unit_according_third = 23.43
    # 利用電気会社
    name_company = 'シン・エナジー株式会社'
    # 引込柱
    ## Sym Energy の場合は不明
    type_pole = ''
    # 使用住居
    name_house = 'ハイネタウン箱崎 #601'

    dict_info = {
        'prev_date': prev_date,
        'this_date': this_date,
        'amount': amount,
        'fee_material': fee_material,
        'fee_basic': fee_basic,
        'fee_unit_according_first': fee_unit_according_first,
        'fee_unit_according_second': fee_unit_according_second,
        'fee_unit_according_third': fee_unit_according_third,
        'fee_renewable_energy': fee_renewable_energy,
        'discount_account': discount_account,
        'rate_tax': rate_tax,
        'tax': tax,
        'name_company': name_company,
        'type_contract': type_contract,
        'type_amount': type_amount,
        'code_customer': ID,
        'fee_total_get': fee_total_get,
        'type_pole': type_pole,
        'name_house': name_house
    }

    return dict_info


def calc_data(dict_info):
    amount = dict_info['amount']  # 使用量
    fee_basic = dict_info['fee_basic']  # 基本料金
    fee_unit_according_first = dict_info['fee_unit_according_first']  # 電力料金単価 (1段階目)
    fee_unit_according_second = dict_info['fee_unit_according_second']  # 電力料金単価 (2段階目)
    fee_unit_according_third = dict_info['fee_unit_according_third']  # 電力料金単価 (2段階目)
    fee_material = dict_info['fee_material']  # 燃料費調整単価
    fee_renewable_energy = dict_info['fee_renewable_energy']  # 再エネ賦課金
    discount_account = dict_info['discount_account']  # 口座振替割引
    fee_total_get = dict_info['fee_total_get']  # 取得した合計請求金額

    # 電力料金 (1段階目)
    ## Sym Energy の場合、120kWhまで
    fee_according_first = int(min([amount, 120]) * fee_unit_according_first)
    # 電力料金 (2段階目)
    ## Sym Energy の場合、121 - 300kWhまで
    fee_according_second = int(max([min([amount, 300])-120, 0]) * fee_unit_according_second)
    # 電力料金 (3段階目)
    ## Sym Energy の場合、301kWh - まで
    fee_according_third = int(max([amount-300, 0]) * fee_unit_according_third)
    # 燃料費調整額
    fee_material_adj = amount * fee_material
    # 合計請求金額
    fee_total_calc = (fee_basic
                      + fee_according_first + fee_according_second + fee_according_third
                      + fee_material_adj + fee_renewable_energy + discount_account)
    fee_total_calc = int(fee_total_calc)
    # 誤差
    diff = fee_total_get - fee_total_calc

    dict_info['fee_according_first'] = fee_according_first
    dict_info['fee_according_second'] = fee_according_second
    dict_info['fee_according_third'] = fee_according_third
    dict_info['fee_material_adj'] = fee_material_adj
    dict_info['fee_total_calc'] = fee_total_calc
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
        fee_electricity
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
    INSERT INTO fee_electricity ({name_columns}) VALUES ({name_values});
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

    # 過去2年間分を取得
    str_query = """
    SELECT 
        year, month, amount, fee_total_get, diff
    FROM
        fee_electricity
    WHERE
        -- 23ヶ月前までのデータを取得
        TO_DATE(CAST(year AS CHARACTER VARYING) || LPAD(CAST(month AS CHARACTER VARYING), 2, '0') || '01', 'YYYYMMDD') >= '{year_before}-{month_before}-01'
        AND TO_DATE(CAST(year AS CHARACTER VARYING) || LPAD(CAST(month AS CHARACTER VARYING), 2, '0') || '01', 'YYYYMMDD') <= '{year}-{month}-01'
        -- AND CAST(month AS SMALLINT) % 2 = 0;
    """
    str_query = str_query.format(year_before=year_before, month_before=month_before, year=year, month=month)

    # Execute
    cur.execute(str_query)
    res = cur.fetchall()

    df_draw = pd.DataFrame(res, columns=['year', 'month', 'amount', 'fee', 'diff'])
    df_draw = df_draw.sort_values(['year', 'month'])
    df_draw['num_series'] = [i for i in range(12)] * 2  # 最新月をグラフの右に表示させるための機構
    df_draw['num_last'] = ['去年'] * 12 + ['今年'] * 12  # 昨年度のデータは薄く表示させるための機構
    # print(df_draw)

    # 描画
    fig, ax1 = plt.subplots(figsize=(20, 10))
    ax2 = ax1.twinx()  # 合計金額
    sns.barplot(data=df_draw, x='num_series', y='amount', hue='num_last', palette=['#BBDEFB', '#2196F3'], ax=ax1)
    sns.lineplot(data=df_draw, x='num_series', y='fee', hue='num_last', palette=['#ffcdd2', '#f44336'], ax=ax2)
    ax1.set_ylim(0, df_draw['amount'].max() + 5)
    ax2.set_ylim(0, df_draw['fee'].max() + 100)
    ## ラベル調整
    ax1.set_title('電気代', fontsize=40)
    ax1.set_ylabel('電気使用量 (kWh)', fontsize=30)
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
    ## 今月と昨年度今月の使用量
    [amount_before, amount] = df_temp['amount'].to_list()
    amount_diff = round(amount - amount_before, 1)
    amount = '{:,}'.format(amount)  # カンマ区切りにする
    if amount_diff >= 0:
        amount_diff = '{:,}'.format(amount_diff)  # カンマ区切りにする
        amount_diff = '+' + str(amount_diff)
    else:
        amount_diff = '{:,}'.format(amount_diff)  # カンマ区切りにする
    ## 今月と昨年度今月の合計金額
    [fee_before, fee] = df_temp['fee'].to_list()
    fee_diff = fee - fee_before
    fee = '{:,}'.format(fee)  # カンマ区切りにする
    if fee_diff >= 0:
        fee_diff = '{:,}'.format(fee_diff)  # カンマ区切りにする
        fee_diff = '+' + str(fee_diff)
    else:
        fee_diff = '{:,}'.format(fee_diff)  # カンマ区切りにする
    ## 実測値 - 観測値の差分
    diff = df_temp['diff'].to_list()[1]
    diff = '{:,}'.format(diff)  # カンマ区切りにする
    message = ('{year}年{month}月 - 電気代が確定！'
               + '\n使用量: {amount}kWh (前年比: {amount_diff}kWh)'
               + '\n合計金額: {fee}円 (前年比: {fee_diff}円)'
               + '\n実測値 - 計算値: {diff}円')
    message = message.format(year=year, month=month,
                             amount=amount, amount_diff=amount_diff, fee=fee, fee_diff=fee_diff, diff=diff)

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

    # Connect Database
    conn, cur = connect_database()

    # 対象の年月が既に Database に書き込まれているか確認
    check_update(year=year, month=month, cur=cur)

    # 書き込む情報をスクレイピングする
    dict_info = get_info(year=year, month=month)

    # 必要なデータを揃える
    dict_info['year'] = year
    dict_info['month'] = month
    dict_info = calc_data(dict_info=dict_info)

    # 書き込み
    insert_data(conn=conn, cur=cur, dict_info=dict_info)

    # グラフを描画
    df_draw = draw_graph(year=year, month=month, cur=cur)

    # メッセージを送信
    send_message(df_draw=df_draw, year=year, month=month)