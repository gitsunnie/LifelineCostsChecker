# -*- coding: utf-8 -*-

"""
参考: https://qiita.com/mSpring/items/257adb27d9170da3b372

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
    url_login = 'https://www.iis-webservice.com/iis-web/user/login'

    ID = os.environ['id_gas']  # 環境変数から ID を読み込み
    PASSWORD = os.environ['password_gas']  # 環境変数から Password を読み込み

    session = requests.session()

    # token の取得
    res = session.get(url_login)
    soup = BeautifulSoup(res.text, 'html.parser')
    _csrf = soup.find(attrs={'name': '_csrf'}).get('value')

    # リクエストパラメータ
    data_login = {
        'userCd2': ID,
        'userCd': ID + ':ROLE_USER',
        'password': PASSWORD,
        '_csrf': _csrf
    }

    # ログインする
    url_dologin = 'https://www.iis-webservice.com/iis-web/user/doLogin'
    session.post(url_dologin, data=data_login)

    # ホームページに移行
    url_bills = 'https://www.iis-webservice.com/iis-web/user/home'
    res = session.get(url_bills)

    # ---

    # 特定の年月を選択
    url_ym = 'https://www.iis-webservice.com/iis-web/user/claim'

    # token の取得
    res = session.get(url_ym)
    soup = BeautifulSoup(res.text, 'html.parser')
    _csrf = soup.find(attrs={'name': '_csrf'}).get('value')

    # リクエストパラメータ
    ym = str(year) + str(month).zfill(2) + '20'
    data_ym = {
        'slctClaimEndDate': ym,
        '_csrf': _csrf
    }

    # 特定の年月に移行
    res = session.post(url_ym, data=data_ym)
    soup = BeautifulSoup(res.text, 'html.parser')
    # print(soup.prettify())

    # 更新チェック
    ## 対象年月のデータが出ているか確認 -> 出ていなかったら終了
    check_title = soup.select_one('head > title').string
    if 'エラー' in check_title:
        print('まだ{year}年{month}月のデータは出ていません'.format(year=year, month=month))
        exit()

    # 必要な項目の取得
    # 今回検針日
    this_date = soup.find(name='th', text='今回検針')
    this_date = this_date.next_sibling.next_sibling.string
    this_date = datetime.datetime.strptime(this_date, '%m/%d')
    # 前回検針日
    prev_date = soup.find(name='th', text='前回検針')
    prev_date = prev_date.next_sibling.next_sibling.string
    prev_date = datetime.datetime.strptime(prev_date, '%m/%d')
    if prev_date.month < this_date.month:
        prev_date = datetime.date(year, prev_date.month, prev_date.day)
    else:
        prev_date = datetime.date(year-1, prev_date.month, prev_date.day)
    this_date = datetime.date(year, this_date.month, this_date.day)

    # 使用量
    amount = soup.find(name='span', text='今回')
    amount = amount.next_sibling.next_sibling.contents[0].string
    amount = float(amount.replace(',', ''))  # 型変換
    # 基本料金
    fee_basic = soup.find(name='th', text='基本料金')
    fee_basic = fee_basic.next_sibling.next_sibling.string
    fee_basic = int(fee_basic.replace(',', ''))  # 型変換
    # ガス基準従量単価
    ## ガス会社により決定
    ## イワタニ九州の場合
    fee_unit_according_first = 693  # 5m3 までの料金
    fee_unit_according_second = 627  # 15m3 までの料金
    # うち消費税
    tax = soup.find(name='span', text='内ガス料金消費税')
    tax = tax.parent.next_sibling.next_sibling.contents[1].string
    tax = int(tax.replace(',', ''))  # 型変換
    # 請求料金
    fee_total_get = soup.find(name='th', text='ガス料金（税込）')
    fee_total_get = fee_total_get.next_sibling.next_sibling.string
    fee_total_get = int(fee_total_get.replace(',', ''))  # 型変換
    # その他, イワタニ九州の場合は固定値
    # 原料費
    fee_material = 0
    # 原料費調整金額
    fee_material_adj = 0
    # 消費税率
    rate_tax = 0.1
    # 利用ガス会社
    name_company = 'イワタニ九州 株式会社'
    # 使用住居
    name_house = 'ハイネタウン箱崎 #601'

    dict_info = {
        'prev_date': prev_date,
        'this_date': this_date,
        'amount': amount,
        'fee_basic': fee_basic,
        'fee_unit_according_first': fee_unit_according_first,
        'fee_unit_according_second': fee_unit_according_second,
        'tax': tax,
        'fee_total_get': fee_total_get,
        'fee_material': fee_material,
        'fee_material_adj': fee_material_adj,
        'rate_tax': rate_tax,
        'name_company': name_company,
        'name_house': name_house
    }

    return dict_info


def calc_data(dict_info):
    amount = dict_info['amount']  # 使用量
    fee_basic = dict_info['fee_basic']  # 基本料金
    fee_unit_according_first = dict_info['fee_unit_according_first']  # ガス基準従量単価 (1段階目)
    fee_unit_according_second = dict_info['fee_unit_according_second']  # ガス基準従量単価 (2段階目)
    fee_total_get = dict_info['fee_total_get']  # 取得した合計請求金額

    # ガス従量料金 (1段階目)
    ## イワタニ九州の場合、5.0m3まで
    fee_according_first = int(min([amount, 5]) * fee_unit_according_first)
    # ガス従量料金 (2段階目)
    ## イワタニ九州の場合、15.0m3まで
    fee_according_second = int(max([amount-5, 0]) * fee_unit_according_second)
    # 合計請求金額
    fee_total_calc = fee_basic + fee_according_first + fee_according_second
    # 誤差
    diff = fee_total_get - fee_total_calc

    dict_info['fee_according_first'] = fee_according_first
    dict_info['fee_according_second'] = fee_according_second
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
        fee_gas
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
    INSERT INTO fee_gas ({name_columns}) VALUES ({name_values});
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
        fee_gas
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
    ax1.set_title('ガス代', fontsize=40)
    ax1.set_ylabel('ガス使用量 (㎥)', fontsize=30)
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
    message = ('{year}年{month}月 - ガス代が確定！'
               + '\n使用量: {amount}㎥ (前年比: {amount_diff}㎥)'
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
