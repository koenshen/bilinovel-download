import os
import zipfile
import shutil
import glob

# 定义要替换的CSS样式内容
new_style_content = """<style>
    /* 页面默认设置 */
    body {
        margin-top: -60px;
        margin-bottom: -60px;
        margin-left: -70px;
        margin-right: -70px;
    }

    /*正文段落缺省格式*/
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
for root, dirs, files in os.walk('C:\\Users\\11018\\Documents\\bili_novel\\test'):
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
            if file.lower().endswith('.xhtml'):
                xhtml_path = os.path.join(root_dir, file)
                try:
                    # 读取文件内容并替换样式
                    with open(xhtml_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    old_style = '<style>p { text-indent: 2em; }</style>'
                    if old_style in content:
                        content = content.replace(old_style, new_style_content)

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