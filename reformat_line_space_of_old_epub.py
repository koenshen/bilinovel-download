import os,re
import zipfile
import shutil
import glob

# 定义要替换的CSS样式内容
new_style_content = """<style>
html {
        margin-top: -60px;
        margin-bottom: -80px;
        margin-left: -55px;
        margin-right: -55px;
 }

p {
        text-indent: 2em;    /* 首行缩进 */
        line-height: 100%;   /* 行距 */
        text-align: justify; /* 文本对齐方式 */
        margin-top: 0em;     /* 段落间距 */
        margin-bottom: 0.5em;
}
</style>"""

# 递归查找所有epub文件
epub_files = []
for root, dirs, files in os.walk('D:\\bili_novel\\copy'):
    for file in files:
        if file.lower().endswith('.epub'):
            epub_files.append(os.path.join(root, file))

# 处理每个epub文件
for epub_path in epub_files:
    # 步骤1: 重命名epub为zip
    zip_path = os.path.splitext(epub_path)[0] + '.zip'
    os.rename(epub_path, zip_path)

    # 步骤2: 解压zip文件
    extract_dir = os.path.splitext(zip_path)[0]
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    # 步骤3: 查找并修改所有xhtml文件
    for root_dir, _, files in os.walk(extract_dir):
        for file in files:
            file_name = file.lower()
            # 去除epub文件源代码中重复的名字
            if "content.opf" in file_name:
                # 读取文件内容
                with open(os.path.join(root_dir, file_name), 'r', encoding='utf-8') as file:
                    content = file.read()
                # 定义正则表达式匹配模式
                pattern = r'(<dc:title>)(.*?)(</dc:title>)'
                # 查找并处理标题
                def process_title(match):
                    prefix = match.group(1)  # 匹配开标签 <dc:title>
                    title_text = match.group(2)  # 匹配标题内容
                    suffix = match.group(3)  # 匹配闭标签 </dc:title>
                    # 按第一个横杠分割并取后半部分
                    if '-' in title_text:
                        new_text = title_text.split('-', 1)[1]  # 分割一次，取后半部分
                    else:
                        new_text = title_text  # 无横杠则保留原内容
                    # 返回新标题格式
                    return prefix + new_text + suffix
                # 执行正则替换
                new_content = re.sub(pattern, process_title, content)
                # 将修改后的内容写回文件
                with open(os.path.join(root_dir, file_name), 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print("文件修改完成！")

            if file_name.endswith('.xhtml'):
                xhtml_path = os.path.join(root_dir, file)
                try:
                    # 读取文件内容并替换样式
                    with open(xhtml_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    old_style = '<style>p { text-indent: 2em; }</style>'
                    if "cover" not in xhtml_path and "color" not in xhtml_path:
                        if old_style in content:
                            content = content.replace(old_style, new_style_content)
                        else:
                            print("has not exist old_style")
                    # 写回修改后的内容
                    with open(xhtml_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                except Exception as e:
                    print(f"处理文件 {xhtml_path} 时出错: {str(e)}")

    # 步骤4: 创建新的zip文件
    new_zip_path = extract_dir + '_new.zip'
    with zipfile.ZipFile(new_zip_path, 'w', zipfile.ZIP_DEFLATED) as new_zip:
        for root_dir, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root_dir, file)
                arcname = os.path.relpath(file_path, extract_dir)
                new_zip.write(file_path, arcname)

    # 步骤5: 重命名为新的epub文件
    new_epub_path = os.path.splitext(zip_path)[0] + '.epub'
    os.rename(new_zip_path, new_epub_path)

    print(f"已处理: {epub_path} -> {new_epub_path}")

print("所有epub文件处理完成！")