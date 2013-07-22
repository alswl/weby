# coding=utf8

from datetime import datetime, date
import json


def format_dic(dic):
    """将 dic 格式化为 JSON，处理日期等特殊格式"""
    for key, value in dic.iteritems():
        dic[key] = format_value(value)
    return dic


def format_value(value, include_fields=[], is_compact=True):
    if isinstance(value, dict):
        return format_dic(value)
    elif isinstance(value, list):
        return format_list(value)
    elif isinstance(value, datetime):
        return value.isoformat()
    #elif isinstance(value, bool):
        #return 1 if value else 0
    elif hasattr(value, 'to_api_dic'):
        return value.to_api_dic(include_fields, is_compact)
    else:
        try:
            json.dumps(value)
            return value
        except:
            return unicode(value)


def format_list(l):
    return [format_value(x) for x in l]
