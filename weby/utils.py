# coding=utf8

from datetime import datetime, date


def format_dic(dic):
    """将 dic 格式化为 JSON，处理日期等特殊格式"""
    for key, value in dic.iteritems():
        dic[key] = format_value(value)
    return dic


def format_value(value):

    if isinstance(value, dict):
        return format_dic(value)
    elif isinstance(value, list):
        return format_list(value)

    elif isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, date):
        return value.isoformat()
    #elif isinstance(value, API_V1_Mixture):
        #return value.to_api_dic(is_compact=True)
    else:
        return value


def format_list(l):
    return [format_value(x) for x in l]
