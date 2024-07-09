from tool import update_ui, promote_file_to_downloadzone, disable_auto_promotion
from tool import CatchException, report_exception, write_history_to_file
from .functional import input_clipping, get_token_num
from yapf.yapflib.yapf_api import FormatCode
import subprocess
import shutil
import os
import re

def format_python_file(filepath, file_content):
    '''
    格式化Python代码文件
    '''
    shutil.copy(filepath, f'{filepath}.temp')
    if not os.path.exists(f'{filepath}.temp'):
        raise Exception(f'File {filepath}.temp does not exist')
    command = f"autoflake --remove-unused-variables --in-place --remove-all-unused-imports {filepath}.temp"
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            output = open(f'{filepath}.temp', 'r', encoding='utf-8').read()
        else:
            output = result.stderr.strip()
    except Exception as e:
        output = str(e)
    # print(output)
    os.remove(f'{filepath}.temp')
    style = {
    'indent_width': 2,
    'use_tabs': False,
    'split_before_logical_operator': False,
    'EACH_DICT_ENTRY_ON_SEPARATE_LINE': False,
    'BLANK_LINE_BEFORE_NESTED_CLASS_OR_DEF':False,
    'ALLOW_SPLIT_BEFORE_DEFAULT_OR_NAMED_ASSIGNS':False,
    'ALLOW_SPLIT_BEFORE_DICT_VALUE':False,
    'BLANK_LINES_AROUND_TOP_LEVEL_DEFINITION':1,
    'COLUMN_LIMIT':1000
}
    formatted_code, changed = FormatCode(output, style_config=style)
    # print(len(file_content), len(output), len(formatted_code))
    # for each in FormatCode(file_content, print_diff=True):
    #     print(each)
    # exit()
    return formatted_code

# # 得到代码文件中声明和使用的函数
# def find_function(file_content, filename, project_folder, func_dec, func_use):
#     re_dec = re.compile(r'def ([^\s\.]*)\(')
#     re_use = re.compile(r'from ([^\s]*?) import ([^\n]*)')
#     result_dec = re.findall(re_dec, file_content)
#     result_use = re.findall(re_use, file_content)
#     func_dec[filename] = []
#     for each in result_dec:
#         func_dec[filename].append(each)
        
#     func_use[filename] = {}
#     for each in result_use:
#         module = each[0]
#         if module.startswith('.'):
#             module = '/'.join(filename.split('/')[:-1]) + '/' + module
#         elif '.' in module:
#             module = module.replace('.', '/')
#         else:
#             pass
#         print(module)
#         module = module + '.py'
#         if module not in func_use[filename]:
#             func_use[filename][module] = []
#         func_use[filename][module].extend([x.strip() for x in each[1].split(',')])
        
#     return func_dec, func_use

def find_func_dec(file_content, filename, func_dec):
    re_dec = re.compile(r'def ([^\s\.]*?)\(')
    result_dec = re.findall(re_dec, file_content)
    re_dec = re.compile(r'class ([^\s\.]*?)\(')
    result_dec += re.findall(re_dec, file_content)
    for each in result_dec:
        if each not in func_dec:
            func_dec[each] = []
        func_dec[each].append(filename) # 先这样写了，两个文件有同名函数的情况没有处理好
    return func_dec

def find_related_file(file_content, func_dec):
    related_file = []
    re_use = re.compile(r'from ([^\s]*?) import ([^\n]*)')
    result_use = re.findall(re_use, file_content)
    for each in result_use:
        for func in each[1].split(','):
            if func.strip() in func_dec:
                related_file.extend(func_dec[func.strip()])
    return related_file

# 按照group来划分代码文件，添加一个个group直到超过token限制
def clip_this_iteration_file_manifest(force, this_iteration_file_manifest, gpt_response_collection, all_file_rel_path, previous_iteration_files, summary_batch_isolation, max_token_limit):
    this_iteration_gpt_response_collection = []
    for filename in this_iteration_file_manifest:
        this_iteration_gpt_response_collection.append(gpt_response_collection[all_file_rel_path.index(filename)*2])
        this_iteration_gpt_response_collection.append(gpt_response_collection[all_file_rel_path.index(filename)*2 + 1])
    file_rel_path = this_iteration_file_manifest
        # 把“请对下面的程序文件做一个概述” 替换成 精简的 "文件名：{all_file[index]}"
    for index, content in enumerate(this_iteration_gpt_response_collection):
        if index%2==0: this_iteration_gpt_response_collection[index] = f"{file_rel_path[index//2]}" # 只保留文件名节省token
    # print(this_iteration_gpt_response_collection)
    # exit()
    this_iteration_files = this_iteration_file_manifest
    previous_iteration_files.extend(this_iteration_files)
    previous_iteration_files = list(set(previous_iteration_files))
    previous_iteration_files_string = ', '.join(previous_iteration_files)
    current_iteration_focus = ', '.join(this_iteration_files)
    if summary_batch_isolation: focus = current_iteration_focus
    else:                       focus = previous_iteration_files_string
    i_say = f'用一张Markdown表格简要描述以下文件的功能：{focus}。根据以上分析，用一句话概括程序的整体功能。'
    everything = [i_say] + this_iteration_gpt_response_collection
    tokens = get_token_num('\n'.join(this_iteration_gpt_response_collection))
    if tokens < max_token_limit or force: # 至少要有一组输入
        return previous_iteration_files, current_iteration_focus, this_iteration_gpt_response_collection, i_say, this_iteration_files
    else: 
        return previous_iteration_files, None, [], i_say, []

def 解析源代码新(file_manifest, project_folder, llm_kwargs, plugin_kwargs, history, system_prompt):
    import os, copy
    from .functional import request_gpt_model_multi_threads_with_very_awesome_ui_and_high_efficiency
    from .functional import request_gpt_model_in_new_thread_with_ui_alive
    summary_batch_isolation = False
    inputs_array = []
    inputs_show_user_array = []
    history_array = []
    sys_prompt_array = []
    report_part_1 = []
    func_dec, func_use = {}, {}
    assert len(file_manifest) <= 512, "源文件太多（超过512个）, 请缩减输入文件的数量。或者，您也可以选择删除此行警告，并修改代码拆分file_manifest列表，从而实现分批次处理。"
    ############################## <第一步，逐个文件分析，多线程> ##################################
    for index, fp in enumerate(file_manifest):
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            file_content = f.read()
        simple_name = os.path.relpath(fp, project_folder)
        # 查找文件调用和声明的函数
        func_dec = find_func_dec(file_content=file_content, filename=simple_name, func_dec=func_dec)
    # print(func_use, func_dec)
    # print(func_dec)
    # exit()
    related_files = []
    for index, fp in enumerate(file_manifest):
        # 读取文件
        simple_name = os.path.relpath(fp, project_folder)
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            file_content = f.read()
            if fp.endswith('.py'):
                file_content = format_python_file(filepath=fp, file_content=file_content)
        related_file = find_related_file(file_content, func_dec)
        # for name in func_use:
        #     # 列表前端插入当前文件引用的文件，后端插入当前文件被引用的文件名
        #     if name == simple_name:
        #         for decfile, funcs in func_use[name].items():
        #             for func in funcs:
        #                 if func in func_dec[decfile]:
        #                     related_file.insert(0, decfile)
        #     else:
        #         if simple_name in func_use[name] and any(func in func_dec[simple_name] for func in func_use[name][simple_name]):
        #             related_file.append(name)
 
        related_file.insert(0, simple_name)
        related_file = list(set(related_file))
        # print(related_file)
        # print(related_file)
        related_files.append(related_file)
        prefix = "接下来请你逐文件分析下面的工程" if index==0 else ""
        i_say = prefix + f'请对下面的程序文件做一个概述文件名是{simple_name}，文件代码是 ```{file_content}```'
        i_say_show_user = prefix + f'[{index}/{len(file_manifest)}] 请对下面的程序文件做一个概述: {fp}'
        # 装载请求内容
        inputs_array.append(i_say)
        inputs_show_user_array.append(i_say_show_user)
        history_array.append([])
        sys_prompt_array.append("你是一个程序架构分析师，正在分析一个源代码项目。你的回答必须简单明了。")
    # exit()
    # 文件读取完成，对每一个源代码文件，生成一个请求线程，发送到chatgpt进行分析
    # print(related_files)
    gpt_response_collection = request_gpt_model_multi_threads_with_very_awesome_ui_and_high_efficiency(
        inputs_array = inputs_array,
        inputs_show_user_array = inputs_show_user_array,
        history_array = history_array,
        sys_prompt_array = sys_prompt_array,
        llm_kwargs = llm_kwargs,
        show_user_at_complete = True
    )

    # 全部文件解析完成，结果写入文件，准备对工程源代码进行汇总分析
    report_part_1 = copy.deepcopy(gpt_response_collection)
    history_to_return = report_part_1
    res = write_history_to_file(report_part_1)
    # promote_file_to_downloadzone(res, chatbot=chatbot)
    # chatbot.append(("完成？", "逐个文件分析已完成。" + res + "\n\n正在开始汇总。"))

    ############################## <第二步，综合，单线程，分组+迭代处理> ##################################
    report_part_2 = []
    previous_iteration_files = []
    last_iteration_result = ""
    finished = [0] * len(file_manifest)
    all_file_rel_path = [os.path.relpath(fp, project_folder) for index, fp in enumerate(file_manifest)]
    force = False
    while True:
        if not any(x == 0 for x in finished): break
        this_iteration_file_manifest = []
        for group in related_files:
            # 不断添加group直到超过token限制
            if not finished[all_file_rel_path.index(group[0])]: # 当前group的中心文件已经还没有分析过，则可以加入
                tmp_list = copy.deepcopy(this_iteration_file_manifest)
                tmp_previous_list = copy.deepcopy(previous_iteration_files)
                tmp_list.extend(group)
                tmp_list = list(set(tmp_list))
                tmp_previous_list, current_iteration_focus, this_iteration_gpt_response_collection, i_say, this_iteration_files = clip_this_iteration_file_manifest(force, tmp_list, gpt_response_collection, all_file_rel_path, tmp_previous_list, summary_batch_isolation, max_token_limit=2500)
                if current_iteration_focus is None:
                    if len(this_iteration_file_manifest) == 0:
                        force = True
                        _, current_iteration_focus, this_iteration_gpt_response_collection, i_say, this_iteration_files = clip_this_iteration_file_manifest(force, tmp_list, gpt_response_collection, all_file_rel_path, previous_iteration_files, summary_batch_isolation, max_token_limit=2500)
                        force = False
                    else:
                        _, current_iteration_focus, this_iteration_gpt_response_collection, i_say, this_iteration_files = clip_this_iteration_file_manifest(force, this_iteration_file_manifest, gpt_response_collection, all_file_rel_path, previous_iteration_files, summary_batch_isolation, max_token_limit=2500)
                    break
                else:
                    this_iteration_file_manifest = copy.deepcopy(tmp_list)
                    previous_iteration_files = copy.deepcopy(tmp_previous_list)
        print(previous_iteration_files, current_iteration_focus, this_iteration_gpt_response_collection, i_say, this_iteration_files)
        for filename in this_iteration_file_manifest:
            finished[all_file_rel_path.index(filename)] = 1
        
        if last_iteration_result != "":
            sys_prompt_additional = "已知某些代码的局部作用是:" + last_iteration_result + "\n请继续分析其他源代码，从而更全面地理解项目的整体功能。"
        else:
            sys_prompt_additional = ""
        inputs_show_user = f'根据以上分析，对程序的整体功能和构架重新做出概括，由于输入长度限制，可能需要分组处理，本组文件为 {current_iteration_focus} + 已经汇总的文件组。'
        this_iteration_history = copy.deepcopy(this_iteration_gpt_response_collection)
        this_iteration_history.append(last_iteration_result)
        # 裁剪input
        inputs, this_iteration_history_feed = input_clipping(inputs=i_say, history=this_iteration_history, max_token_limit=2560)
        result = request_gpt_model_in_new_thread_with_ui_alive(
            inputs=inputs, inputs_show_user=inputs_show_user, llm_kwargs=llm_kwargs,
            history=this_iteration_history_feed,   # 迭代之前的分析
            sys_prompt="你是一个程序架构分析师，正在分析一个项目的源代码。" + sys_prompt_additional)

        diagram_code = make_diagram(this_iteration_files, result, this_iteration_history_feed)
        summary = "请用一句话概括这些文件的整体功能。\n\n" + diagram_code
        summary_result = request_gpt_model_in_new_thread_with_ui_alive(
            inputs=summary,
            inputs_show_user=summary,
            llm_kwargs=llm_kwargs,
            history=[i_say, result],   # 迭代之前的分析
            sys_prompt="你是一个程序架构分析师，正在分析一个项目的源代码。" + sys_prompt_additional)

        report_part_2.extend([i_say, result])
        last_iteration_result = summary_result

    ############################## <END> ##################################
    history_to_return.extend(report_part_2)
    res = write_history_to_file(history_to_return)
    # promote_file_to_downloadzone(res, chatbot=chatbot)
    # chatbot.append(("完成了吗？", res))

def make_diagram(this_iteration_files, result, this_iteration_history_feed):
    from crazy_functions.diagram_fns.file_tree import build_file_tree_mermaid_diagram
    return build_file_tree_mermaid_diagram(this_iteration_history_feed[0::2], this_iteration_history_feed[1::2], "项目示意图")

@CatchException
def 解析项目本身(txt, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    history = []    # 清空历史，以免输入溢出
    import glob
    file_manifest = [f for f in glob.glob('./*.py')] + \
                    [f for f in glob.glob('./*/*.py')]
    project_folder = './'
    if len(file_manifest) == 0:
        raise Exception('找不到任何python文件')
        return
    yield from 解析源代码新(file_manifest, project_folder, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt)


def 解析一个Python项目(txt, llm_kwargs, plugin_kwargs, history, system_prompt, user_request):
    history = []    # 清空历史，以免输入溢出
    import glob, os
    if os.path.exists(txt):
        project_folder = txt
    else:
        if txt == "": txt = '空空如也的输入栏'
        raise Exception('找不到本地项目或无权访问')
        return
    file_manifest = [f for f in glob.glob(f'{project_folder}/**/*.py', recursive=True)]
    if len(file_manifest) == 0:
        raise Exception('找不到任何python文件')
        return
    return 解析源代码新(file_manifest, project_folder, llm_kwargs, plugin_kwargs, history, system_prompt)

def 解析一个Java项目(txt, llm_kwargs, plugin_kwargs, history, system_prompt, user_request):
    history = []  # 清空历史，以免输入溢出
    import glob, os
    if os.path.exists(txt):
        project_folder = txt
    else:
        if txt == "": txt = '空空如也的输入栏'
        raise Exception('找不到本地项目或无权访问')
    file_manifest = [f for f in glob.glob(f'{project_folder}/**/*.java', recursive=True)] + \
                    [f for f in glob.glob(f'{project_folder}/**/*.jar', recursive=True)] + \
                    [f for f in glob.glob(f'{project_folder}/**/*.xml', recursive=True)] + \
                    [f for f in glob.glob(f'{project_folder}/**/*.sh', recursive=True)]
    if len(file_manifest) == 0:
        raise Exception('找不到任何java文件')
    return 解析源代码新(file_manifest, project_folder, llm_kwargs, plugin_kwargs, history, system_prompt)

@CatchException
def 解析任意code项目(txt, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    txt_pattern = plugin_kwargs.get("advanced_arg")
    txt_pattern = txt_pattern.replace("，", ",")
    # 将要匹配的模式(例如: *.c, *.cpp, *.py, config.toml)
    pattern_include = [_.lstrip(" ,").rstrip(" ,") for _ in txt_pattern.split(",") if _ != "" and not _.strip().startswith("^")]
    if not pattern_include: pattern_include = ["*"] # 不输入即全部匹配
    # 将要忽略匹配的文件后缀(例如: ^*.c, ^*.cpp, ^*.py)
    pattern_except_suffix = [_.lstrip(" ^*.,").rstrip(" ,") for _ in txt_pattern.split(" ") if _ != "" and _.strip().startswith("^*.")]
    pattern_except_suffix += ['zip', 'rar', '7z', 'tar', 'gz'] # 避免解析压缩文件
    # 将要忽略匹配的文件名(例如: ^README.md)
    pattern_except_name = [_.lstrip(" ^*,").rstrip(" ,").replace(".", r"\.") # 移除左边通配符，移除右侧逗号，转义点号
                           for _ in txt_pattern.split(" ") # 以空格分割
                           if (_ != "" and _.strip().startswith("^") and not _.strip().startswith("^*."))   # ^开始，但不是^*.开始
                           ]
    # 生成正则表达式
    pattern_except = r'/[^/]+\.(' + "|".join(pattern_except_suffix) + ')$'
    pattern_except += '|/(' + "|".join(pattern_except_name) + ')$' if pattern_except_name != [] else ''

    history.clear()
    import glob, os, re
    if os.path.exists(txt):
        project_folder = txt
    else:
        if txt == "": txt = '空空如也的输入栏'
        raise Exception('找不到本地项目或无权访问')
        return
    # 若上传压缩文件, 先寻找到解压的文件夹路径, 从而避免解析压缩文件
    maybe_dir = [f for f in glob.glob(f'{project_folder}/*') if os.path.isdir(f)]
    if len(maybe_dir)>0 and maybe_dir[0].endswith('.extract'):
        extract_folder_path = maybe_dir[0]
    else:
        extract_folder_path = project_folder
    # 按输入的匹配模式寻找上传的非压缩文件和已解压的文件
    file_manifest = [f for pattern in pattern_include for f in glob.glob(f'{extract_folder_path}/**/{pattern}', recursive=True) if "" != extract_folder_path and \
                      os.path.isfile(f) and (not re.search(pattern_except, f) or pattern.endswith('.' + re.search(pattern_except, f).group().split('.')[-1]))]
    if len(file_manifest) == 0:
        raise Exception('找不到任何文件')
        return
    return 解析源代码新(file_manifest, project_folder, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt)
    
