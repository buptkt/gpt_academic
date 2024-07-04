from crazy_functions.code2text import 解析一个Python项目, 解析一个Java项目
import re

if __name__ == "__main__":
    '''
    txt:用户输入项目路径
    llm_kwargs：参数
    plugin_kwargs：插件参数
    chatbot：
    history
    system_prompt
    user_request
    '''
    # filecontent = open('/data/sdb2/lkt/gpt_academic-master/crazy_functions/code2text.py', 'r', encoding='utf-8').read()
    # find_function(filecontent)
    # exit()
    
    txt = '/d1/kangtong/gpt_academic-master/Java-master/PullBookinfo'
    llm_kwargs = {
            'api_key': 'sk-unDJWEuiSra9bwV1B8B281Ca775142B3B804Af039aD7C461',
            'llm_model': 'gpt-4o',
            'top_p': 1,
            'max_length': 4096,
            'temperature': 1,
            'client_ip': '',
            'most_recent_uploaded': None
        }
    plugin_advanced_arg = ''
    plugin_kwargs = {"advanced_arg": plugin_advanced_arg}
    # 解析一个Java项目(txt, llm_kwargs, plugin_kwargs, history=[], system_prompt=None, user_request=None)
    
    txt = '/data/sdb2/lkt/eeqga/PAIE-main'
    解析一个Python项目(txt, llm_kwargs, plugin_kwargs, history=[], system_prompt=None, user_request=None)
    
    
    