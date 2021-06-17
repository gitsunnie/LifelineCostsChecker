# -*- coding: utf-8 -*-

"""
参考: https://qiita.com/mSpring/items/257adb27d9170da3b372

"""

from bs4 import BeautifulSoup
import urllib.request as req
import requests
from urllib.error import HTTPError

import psycopg2

import datetime


def get_info(year, month):
    url_login = 'https://www.iis-webservice.com/iis-web/user/login'

    ID = 'shinya.fujisaki@outlook.jp'
    PASSWORD = 'goosIwatani1896'

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
    # soup = BeautifulSoup(res.text, 'html.parser')
    # print(soup.prettify())
    # print('\n\n\n\n')

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

    # print('今回検針日:', prev_date)
    # print('前回検針日:', this_date)
    # print('使用量:', amount)
    # print('基本料金:', fee_basic)
    # print('うち消費税:', tax)
    # print('請求料金:', fee_total_get)

    return dict_info


def connect_database():
    # Settings
    host = 'ec2-3-233-7-12.compute-1.amazonaws.com'
    port = 5432
    user = 'wfzuoetwdihyqi'
    name_db = 'd503lsfb4jhm6m'
    password = '524d00ddac91653c99d4f889ab7e68b2d5d7a6f96a91212d887b7f3b697821a4'

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


if __name__ == '__main__':
    l = [(2020, 5), (2020, 6), (2020, 7), (2020, 8), (2020, 9), (2020, 10), (2020, 11), (2020, 12),
         (2021, 1), (2021, 2), (2021, 3), (2021, 4), (2021, 5), (2021, 6)]
    # YEAR = 2020
    # MONTH = 4
    for i in l:
        print(i)
        YEAR = i[0]
        MONTH = i[1]

        # Connect Database
        conn, cur = connect_database()

        # 対象の年月が既に Database に書き込まれているか確認
        check_update(year=YEAR, month=MONTH, cur=cur)

        # 書き込む情報をスクレイピングする
        dict_info = get_info(year=YEAR, month=MONTH)

        # 必要なデータを揃える
        dict_info['year'] = YEAR
        dict_info['month'] = MONTH
        dict_info = calc_data(dict_info=dict_info)

        # 書き込み
        insert_data(conn=conn, cur=cur, dict_info=dict_info)
