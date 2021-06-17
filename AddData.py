# -*- coding: utf-8 -*-

"""
水道、ガス、電気のエクセルに書き込んでいた過去のデータをデータベースに書き込む
"""

import pandas as pd
import psycopg2
import datetime


def connect():
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


def water(cur):
    df_data = pd.read_csv('lifeline_costs_water.csv', header=0, encoding='cp932')
    print(df_data)
    # 型変換
    list_comma = ['fee_basic_water', 'fee_total_water', 'fee_basic_sewerage', 'fee_total_sewerage',
                  'fee_total_calc', 'fee_total_get']
    for i in list_comma:
        df_data['{}'.format(i)] = df_data['{}'.format(i)].str.replace(',', '')

    """        
    df_data = df_data.astype({'year': int, 'month': int, 'prev_date': datetime.date, 'this_date': datetime.date,
                              'pipe_size': int, 'usage': str, 'sewerage': str, 'sewerage_basis': str,
                              'amount': int, 'fee_basic_water': int, 'fee_unit_according_water': int,
                              'rate_tax': float, 'fee_total_water': int, 'tax_water': int})
    """
    df_data = df_data.astype({'prev_date': datetime.date, 'this_date': datetime.date})

    list_columns = list(df_data.columns)

    for iindex in list(df_data.index):
        str_query = """
        INSERT INTO fee_water ({name_columns}) VALUES ({name_values});
        """

        list_values_root = list(df_data.loc[iindex, :].values)
        # print(list_columns)
        list_values = []
        # 型に応じて、表記方法を変える
        for i in list_values_root:
            if type(i) == datetime.date:
                list_values.append('DATE' + '\'' + str(i) + '\'')
            elif type(i) == str:
                list_values.append('\'' + i + '\'')  # 文字列であることを示すシングルクォーテーションを入れる
            else:
                list_values.append(str(i))
        # print(list_values)
        str_columns = ', '.join(list_columns)
        str_values = ', '.join(list_values)
        str_query = str_query.format(name_columns=str_columns, name_values=str_values)

        print(str_query)

        # Execute
        cur.execute(str_query)
        conn.commit()
        print(cur.statusmessage)

    return 0


if __name__ == '__main__':
    conn, cur = connect()
    water(cur=cur)

