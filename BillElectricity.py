# -*- coding: utf-8 -*-

"""
参考:
https://qiita.com/fake_engineer_00/items/82c3f63ccb6416fd5fca
https://qiita.com/mSpring/items/257adb27d9170da3b372

"""

from bs4 import BeautifulSoup
import urllib.request as req
import requests
from urllib.error import HTTPError

import time


def something():
    url_login = 'https://www.symenergy.net/symenergy/login'

    USER_NAME = 'T90000067336'
    PASSWORD = 'goosSym1896'

    session = requests.session()
    response = session.get(url_login)

    # BeautifulSoupオブジェクト作成(token取得の為)
    bs = BeautifulSoup(response.text, 'html.parser')

    data_login = {  # リクエストパラメータ
        # '_token': '',
        'login_id': USER_NAME,
        'password': PASSWORD
    }

    # tokenの取得
    authenticity_token = bs.find(attrs={'name': '_token'}).get('value')

    # 取得した token を post するパラメータに追加
    data_login['_token'] = authenticity_token

    # ログインする
    session.post(url_login, data=data_login)
    # time.sleep(2)

    url_bills = 'https://www.symenergy.net/symenergy/meter_readings/65153'
    res = session.get(url_bills)
    # time.sleep(2)
    # print(res.text)

    soup = BeautifulSoup(res.text, 'html.parser')

    list_bills_link = soup.find_all(name='a', text='ブラウザで表示')
    # 0番目の要素が最新の料金明細になる
    url_bills_latest = list_bills_link[0]['href']
    print(url_bills_latest)

    # 最新の料金明細ページにアクセス
    res = session.get(url_bills_latest)
    soup = BeautifulSoup(res.text, 'html.parser')
    # print(soup.prettify())

    # 必要な項目を取得
    # 使用量
    kwh = soup.find(name='span', text='ご使用量')
    kwh = kwh.next_sibling.next_sibling.string
    print('使用量:', kwh)
    # 燃料費調整単価
    fee_fuel = soup.find(name='span', text='燃料費調整')
    fee_fuel = fee_fuel.next_sibling.next_sibling.string
    print('燃料費調整単価:', fee_fuel)
    # 基本料金
    fee_basic = soup.find(name='span', text='基本料金')
    fee_basic = fee_basic.next_sibling.next_sibling.string
    print('基本料金:', fee_basic)
    # 再エネ発電賦課金
    fee_energy = soup.find(name='span', text='再エネ発電賦課金')
    fee_energy = fee_energy.next_sibling.next_sibling.string
    print('再エネ発電賦課金:', fee_energy)
    # 支払方法登録割引 (口座振替割引)
    fee_discount = soup.find(name='span', text='支払方法登録割引')
    fee_discount = fee_discount.next_sibling.next_sibling.string
    print('支払方法登録割引:', fee_discount)
    # （うち消費税相当額）
    fee_tax = soup.find(name='span', text='（うち消費税相当額）')
    fee_tax = fee_tax.next_sibling.next_sibling.string
    print('（うち消費税相当額）:', fee_tax)
    # 利用電気会社
    name_company = 'シン・エナジー株式会社'
    # 契約種別
    name_concent_type = soup.find(name='span', text='ご契約種別')
    name_concent_type = name_concent_type.next_sibling.next_sibling.string
    print('契約種別:', name_concent_type)
    # 契約容量
    volume_concent = soup.find(name='span', text='ご契約')
    volume_concent = volume_concent.next_sibling.next_sibling.string
    print('契約容量:', volume_concent)
    # お客様番号
    number_customer = 'T90000067336'
    # 請求料金
    fee_total = soup.find(name='span', text='請求予定金額')
    fee_total = fee_total.next_sibling.next_sibling.string
    print('請求予定金額:', fee_total)




if __name__ == '__main__':
    something()
