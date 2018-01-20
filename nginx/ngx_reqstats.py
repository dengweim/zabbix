#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
获取nginx运行状态，基于tengine reqstat模块
http://tengine.taobao.org/document_cn/http_reqstat_cn.html
"""


import sys
import json
import os
import time
import pickle
import urllib2
import subprocess
from optparse import OptionParser


parser = OptionParser() 
parser.add_option("-l", "--lld",
                  action="store_true", dest="lld", default=False,
                  help="discovery of zookeeper port")
parser.add_option("-i", "--interval",
                  dest="interval", default=100,
                  help="The interval between script runs")
(options, args) = parser.parse_args()


ZBXPATH = {"prefix": "/usr/local/services/zabbix-3.0.0",
           "conf": "etc/zabbix_agentd.conf",
           "sender": "bin/zabbix_sender",
           "result_path": "/tmp/.zbx_result_{0}.txt",
           "sender_path": "/tmp/.zbx_sender_{0}.txt"}
FIELDS = ('timestamp', 'req.total', 'conn.total', 'bytes.in', 'bytes.out',
          'req.time', 'http.200', 'http.404', 'http.403',  'http.500',
          'http.502','http.503','http.504',  'http.2xx', 'http.3xx', 'http.4xx',
          'http.5xx', 'http.other.status', 'limit')
URL = 'http://127.0.0.1/request_stats?limit=1'


def discovery(data):
    """
    获取nginx所有配置reqstat的域名信息
    """
    hosts = []
    for host in data.split():
        _host = host.split(',')[0]
        hosts += [{'{#DOMAIN}': "{0}".format(_host)}]
    print(json.dumps({'data': hosts}, sort_keys=True, indent=4, separators=(',', ':')))
    sys.exit(0)


def collect(data, zbx_path):
    """
    收集Nginx reqstats运行状态，并按zbx格式写入文件
    """
    all_sender_path = []
    timestamp = time.time()
    tobit = ['bytes.in', 'bytes.out']

    for stats in data.split():
        _stats = stats.split(',')
        host = _stats.pop(0)
        _stats.insert(0,  timestamp)
        stats = dict(zip(FIELDS, map(int, _stats)))
        zbx_result_file = zbx_path['result_path'].format(host)
        zbx_sender_file = zbx_path['sender_path'].format(host)
        
        # 读取或者保存当前数据到文件
        try:
            latest = pickle.load(open(zbx_result_file, 'r'))
        except Exception:
            try:
                pickle.dump(stats, open(zbx_result_file, 'w'))
                continue
            except Exception:
                sys.exit('4')
        req_total = stats['req.total']
        latest_req_total = latest['req.total']
        interval = (stats['timestamp'] - latest['timestamp'])

        # 判断Nginx是否重启；长时间脚本是否没有运行。
        if req_total < latest_req_total or interval > options.interval:
            pickle.dump(stats, open(zbx_result_file, 'w'))
            continue

        # 保存当前数据到文件
        pickle.dump(stats, open(zbx_result_file, 'w'))
        stats.pop('timestamp')

        # 将计算结果按zbx格式写入文件
        with open(zbx_sender_file, 'w') as f:
            for key, value in stats.items():
                value = (value-latest.get(key)) / float(interval)
                if key in tobit: 
                    value *= 8
                if key == 'req.time' and value > 0:
                    req_time = stats[key] - latest[key]
                    req_total = float(stats['req.total'] - latest['req.total'])
                    value = req_time / req_total
                f.write("- ngx.req.stats.{0}[{1}] {2}\n".format(key, host, value))
        all_sender_path.append(zbx_sender_file)

    return all_sender_path


def zbx_send(data, zbx_path):
    zbx_prefix = zbx_path['prefix']
    zbx_conf = os.path.join(zbx_prefix, zbx_path['conf'])
    zbx_sender = os.path.join(zbx_prefix, zbx_path['sender'])
    all_sender = collect(data, zbx_path)

    if not all_sender:
        return 0

    for file in all_sender:
        cmd = "{0} -c {1} -i {2}".format(zbx_sender, zbx_conf, file)
        retval = subprocess.call(cmd, shell=True, 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
    return retval


def main():
    try:
        data = urllib2.urlopen(URL, timeout=1).read()
    except Exception:
        sys.exit('1')
    if options.lld:
        discovery(data)
    retval = zbx_send(data, ZBXPATH)
    print(retval if retval == 0 else 2)


if __name__ == "__main__":
    main()

