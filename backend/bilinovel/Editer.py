#!/usr/bin/python
# -*- coding:utf-8 -*-
from datetime import datetime
import requests  # 用来抓取网页的html源码
from bs4 import BeautifulSoup  # 用于代替正则式 取源码中相应标签中的内容
import time  # 时间相关操作
import os
from rich.progress import track as tqdm
from backend.bilinovel.utils import *
import zipfile
import re
# import pickle
from PIL import Image
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from DrissionPage import Chromium, ChromiumOptions
import tempfile

lock = threading.RLock()

class Editer(object):
    def __init__(self, root_path, book_no='0000', volume_no=1, interval=0, num_thread=1):

        self.url_head = 'https://www.linovelib.com'
        self.header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.67 Safari/537.36 Edg/87.0.664.47', 'referer': self.url_head, 'cookie':'night=1'}

        self.interval = float(interval)/1000
        self.main_page = f'{self.url_head}/novel/{book_no}.html'
        self.cata_page = f'{self.url_head}/novel/{book_no}/catalog'
        self.read_tool_page = f'{self.url_head}/themes/zhmb/js/readtool.js'
        self.color_chap_name = '插图'
        self.color_page_name = '彩页'
        self.html_buffer = dict()
        path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'  # Chrome 路径

        # 这里为什么要先kill掉？因为不先kill掉，那么在两卷之间下载的时候，由于下一卷需要回到小说首页获取信息时，总是会卡住无法跳转导致只能获取到Offscreen Utility Page的页面，所以需要先kill再重新启动，就能避免这个问题
        self.kill_chrome_processes()
        time.sleep(1)

        # 2) 立刻去检查 9222，如果旧的残留在占着，就先报警
        if self.is_port_open('127.0.0.1', 9222):
            print("注意：9222 上已有进程，占用状态！")

        # 3) 启动 DrissionPage 去真正 launch Chrome
        co = ChromiumOptions()
        co.set_browser_path(path)
        co.set_argument('--remote-debugging-port=9222')
        co.set_argument('--no-first-run')
        co.set_argument('--no-default-browser-check')

        # 4) 给 Chrome 几百毫秒去起服务
        browser_proc = Chromium(co)  # 这一步内部会去启动 Chrome
        time.sleep(2)  # 等待 Chrome 监听完 9222

        # 5) 再去连一次
        if not self.is_port_open('127.0.0.1', 9222):
            print("Error: Chrome 启动后，9222 依然没有处于监听状态。说明 --remote-debugging-port 并没有生效。")

        self.tab = browser_proc.latest_tab  # 如果上面端口正常，就应该连上了

        main_html = self.get_html(self.main_page)
        self.get_meta_data(main_html)
            
        self.img_url_map = dict()
        self.volume_no = volume_no

        self.epub_path = root_path
        # self.temp_path = os.path.join(self.epub_path,  'temp_'+ check_chars(self.book_name) + '_' + str(self.volume_no))
        self.temp_path_io = tempfile.TemporaryDirectory()
        self.temp_path = self.temp_path_io.name
    
        self.missing_last_chap_list = []
        self.is_color_page = True
        self.page_url_map = dict()
        self.ignore_urls = []
        self.url_buffer = []
        self.max_thread_num = 8
        self.pool = ThreadPoolExecutor(int(num_thread))
        
    # 获取html文档内容
    def get_html(self, url, is_gbk=False):
        while True:
            self.tab.get(url)
            req = self.tab.html
            re_try_time = 10
            while '<title>Access denied | www.linovelib.com used Cloudflare to restrict access</title>' in req:
                print(f'{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}: 下载频繁，触发反爬，导致无法正确读取{url}的小说信息，需要重新读取{re_try_time}秒后重试....')
                time.sleep(re_try_time)
                self.tab.get(url)
                req = self.tab.html
            if is_gbk:
                req.encoding = 'GBK'       #这里是网页的编码转换，根据网页的实际需要进行修改，经测试这个编码没有问题
            break
        if self.interval>0:
            time.sleep(self.interval)
        return req


    # 关闭所有 chrome 浏览器进程
    def kill_chrome_processes(self):
        import psutil
        for proc in psutil.process_iter(['name']):
            # 判断进程名是否为 chrome（即 chrome.exe）
            if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                try:
                    proc.kill()
                    # print(f"Killed process: {proc.pid} - {proc.info['name']}")
                except Exception as e:
                    print(f"Could not kill process {proc.pid}: {e}")
        print("already kill all chrome process.")


    # 手动看看 某个端口是否 有服务在监听
    def is_port_open(self, host, port):
        import socket, time
        s = socket.socket()
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            s.close()
            return True
        except:
            return False

    def get_html_content(self, url, is_buffer=False):
        if is_buffer:
            while not url in self.html_buffer.keys():
                time.sleep(0.1) 
        if url in self.html_buffer.keys():
            return self.html_buffer[url]
        while True:
            try:
                req=requests.get(url, headers=self.header)
                break
            except Exception as e:
                pass
        lock.acquire()
        self.html_buffer[url] = req.content
        lock.release()
        return req.content
    
    def get_meta_data(self, main_html):
        bf = BeautifulSoup(main_html, 'html.parser')
        self.book_name = bf.find('meta', {"property": "og:novel:book_name"})['content']
        self.author = bf.find('meta', {"property": "og:novel:author"})['content']

        brief = bf.find('div', {"class": "book-dec"})
        brief_to_delete = brief.find('div')
        brief_to_delete.extract() if brief_to_delete is not None else 0
        self.brief = brief.find_all('p')[0].text
        
        book_meta = bf.find('div', class_='book-label')
        self.publisher = book_meta.find('a', class_='label').text
        span_tag = book_meta.find('span')
        self.tag_list = []
        if span_tag:
            for a_tag in span_tag.find_all('a'):
                self.tag_list.append(a_tag.text)
                
        try:
            self.cover_url_back = re.search(r'src=\"(.*?)\"', str(bf.find('div', {"class": "book-img fl"}))).group(1)
        except:
            self.cover_url_back = 'cid'
        
    def make_folder(self):
        os.makedirs(self.temp_path, exist_ok=True)

        self.text_path = os.path.join(self.temp_path, 'OEBPS/Text')
        os.makedirs(self.text_path, exist_ok=True)

        self.img_path = os.path.join(self.temp_path,  'OEBPS/Images')
        os.makedirs(self.img_path, exist_ok=True)
    
    def get_index_url(self):
        self.volume = {}
        self.volume['chap_urls'] = []
        self.volume['chap_names'] = []
        chap_html_list = self.get_chap_list(is_print=False)
        if len(chap_html_list)<self.volume_no:
            print('输入卷号超过实际卷数！')
            return False
        volume_array = self.volume_no - 1
        chap_html = chap_html_list[volume_array]

        self.volume['volume_name'] = chap_html.find('h2', {'class': 'v-line'}).text
        chap_list = chap_html.find_all('li', {'class', 'col-4'})
        for chap_html in chap_list:
            self.volume['chap_names'].append(chap_html.text)
            self.volume['chap_urls'].append(self.url_head + chap_html.find('a').get('href'))
        return True
        
    def get_chap_list(self, is_print=True):
        cata_html = self.get_html(self.cata_page, is_gbk=False)
        bf = BeautifulSoup(cata_html, 'html.parser')
        chap_html_list = bf.find_all('div', {'class', 'volume clearfix'})
        if is_print:
            for chap_no, chap_html in enumerate(chap_html_list):
                print(f'[{chap_no+1}]', chap_html.find('h2', {'class': 'v-line'}).text)
            return
        else:
            return chap_html_list

    def get_page_text(self, content_html):
        is_tansfer_rubbish_code = 'woff2' in content_html
        # is_tansfer_rubbish_code = ('font-family: "read"' in content_html)
        bf = BeautifulSoup(content_html, 'html.parser')
        text_with_head = bf.find('div', {'id': 'TextContent'})
        
        self.remove_element(text_with_head, id='show-more-images')
        self.remove_element(text_with_head, class_='google-auto-placed ap_container')
        self.remove_element(text_with_head, class_='dag')
        self.remove_element(text_with_head, id='hidden-images')
        text_html = str(text_with_head)
        # 删除匹配到的内容
        pattern = re.compile(r'<!--(.*?)-->', re.DOTALL)
        text_html = pattern.sub('', text_html)
        
        img_urlre_list = re.findall(r"<img .*?>", text_html)
        for img_urlre in img_urlre_list:
            img_url_full = re.search(r'.[a-zA-Z]{3}/(.*?).(jpg|png|jpeg)', img_urlre)
            img_url_name = img_url_full.group(1)
            img_url_tail = img_url_full.group(0).split('.')[-1]
            img_url = f'https://img3.readpai.com/{img_url_name}.{img_url_tail}'

            if not img_url in self.img_url_map:
                self.img_url_map[img_url] = str(len(self.img_url_map)).zfill(2)
            img_symbol = f'  <img alt=\"{self.img_url_map[img_url]}\" src=\"../Images/{self.img_url_map[img_url]}.jpg\"/>\n'
            if '00' in img_symbol:
                text_html = text_html.replace(img_urlre, '')  #默认第一张为封面图片 不写入彩页
            else:
                text_html = text_html.replace(img_urlre, img_symbol)
                symbol_index = text_html.index(img_symbol)
                if text_html[symbol_index-1] != '\n':
                    text_html = text_html[:symbol_index] + '\n' + text_html[symbol_index:]
        
        text = BeautifulSoup(text_html, 'html.parser').find('div', id='TextContent')
   

        #删除反爬提示元素
        match = re.findall(r'<p(\d+)>', str(text))
        if len(match) > 0:
            warn_element = text.find(f'p{match[0]}')
            warn_element.decompose()  

       
        text = text.decode_contents()
        if text.startswith('\n'):
            text = text[1:]
        if text.endswith('\n\n'):
            text = text[:-1]

        msg = '<br/><br/><br/>————————————以下为告示，读者请无视——————————————<p>'
        text = text[:text.find(msg)]

        # 轻小说过度换行，导致排版很难看。实际上<p></p>已经具有换行的能力了，不需要<br/>了
        text = text.replace('''</p>\n<br/>\n<p>''', '''</p>\n<p>''')

        #去除乱码
        if is_tansfer_rubbish_code:
            text = replace_rubbish_text(text)
        return text

    def remove_element(self, bf_item, id=None, class_=None):
        if id is not None:
            remove_list = bf_item.find_all(id=id)
        elif class_ is not None:
            remove_list = bf_item.find_all(class_=class_)
        for remove_element in remove_list:
            remove_element.decompose()

    def get_chap_text(self, url, chap_name, return_next_chapter=False):
        text_chap = ''
        page_no = 1 
        url_ori = url
        next_chap_url = None

        # 从外部获取的章节名可能是有规避关键词的，比如"女主角"总是被写成"N主角"，只有在这个url获取到的<h1></h1>中拿到的标题名，才是真的标题名
        real_chap_name = chap_name

        while True:

            content_html = self.get_html(url, is_gbk=False)
            if page_no == 1:
                str_out = chap_name
                real_chap_name = content_html.split("<h1>")[1].split("</h1>")[0]
            else:
                str_out = f'    已完成下载第{page_no}页......'
            print(str_out)

            text = self.get_page_text(content_html)
            text_chap += text
            url_new = url_ori.replace('.html', '_{}.html'.format(page_no+1))[len(self.url_head):]
            if url_new in content_html:
                page_no += 1
                url = self.url_head + url_new
            else:
                if return_next_chapter:
                    next_chap_url = self.url_head + re.search(r'书签</a><a href="(.*?)">下一页</a>', content_html).group(1)
                break
        return text_chap, next_chap_url, real_chap_name
    
    def get_text(self):
        self.make_folder()   
        repeat_img_strs = [] #记录重复的图片
        text_no=0   #text_no正文章节编号(排除插图)   chap_no 是所有章节编号
        for chap_no, (chap_name, chap_url) in enumerate(zip(self.volume['chap_names'], self.volume['chap_urls'])):
            is_fix_next_chap_url = (chap_name in self.missing_last_chap_list)
            text, next_chap_url, real_chap_name = self.get_chap_text(chap_url, chap_name, return_next_chapter=is_fix_next_chap_url)

            # 从外部获取的章节名可能是有规避关键词的，比如"女主角"总是被写成"N主角"，只有在这个url获取到的<h1></h1>中拿到的标题名，才是真的标题名。所以要在这里根据下标改正
            # self.volume['chap_names'][chap_no] = real_chap_name

            if chap_name == self.color_chap_name:
                text_html_color = text2htmls(self.color_page_name, text)                
            else:
                file_name = os.path.join(self.text_path, f'{str(text_no).zfill(2)}.xhtml')
                text_html = text2htmls(chap_name, text)
                text_no += 1
                with open(file_name, 'w+', encoding='utf-8') as f:
                    f.write(text_html)
                repeat_img_strs += re.findall(r'<img alt="[^"]*" src="../Images/\d+.jpg"/>', text_html)

            if is_fix_next_chap_url: 
                self.volume['chap_urls'][chap_no+1] = next_chap_url #正向修复
        
        # 将彩页中后文已经出现的图片删除，避免重复
        if self.is_color_page: #判断彩页是否存在
            text_html_color_new = []
            textfile = self.text_path + '/color.xhtml'
            for img_line in repeat_img_strs:
                if img_line in text_html_color:
                    text_html_color = text_html_color.replace(img_line+'\n', '')
        
            with open(textfile, 'w+', encoding='utf-8') as f:
                f.write(text_html_color)

    def get_image(self, is_gui=False, signal=None):
        for url in self.img_url_map.keys():
            self.pool.submit(self.get_html_content, url)
        img_path = self.img_path
        if is_gui:
            len_iter = len(self.img_url_map.items())
            signal.emit('start')
            for i, (img_url, img_name) in enumerate(self.img_url_map.items()):
                content = self.get_html_content(img_url, is_buffer=True)
                with open(img_path+f'/{img_name}.jpg', 'wb') as f:
                    f.write(content) #写入二进制内容 
                signal.emit(int(100*(i+1)/len_iter))
            signal.emit('end')
        else:
            for img_url, img_name in tqdm(self.img_url_map.items()):
                content = self.get_html_content(img_url)
                with open(img_path+f'/{img_name}.jpg', 'wb') as f:
                    f.write(content) #写入二进制内容

    def get_cover(self, is_gui=False, signal=None):
        img_w, img_h = 300, 300
        try:
            imgfile = os.path.join(self.img_path, '00.jpg')
            img = Image.open(imgfile)
            img_w, img_h = img.size
            signal_msg = (imgfile, img_h, img_w)
            if is_gui:
                signal.emit(signal_msg)
        except Exception as e:
            print(e)
            print('没有封面图片，请自行用第三方EPUB编辑器手动添加封面')
        with open(os.path.join(self.text_path, 'cover.xhtml'), 'w+', encoding='utf-8') as f:
            f.write(get_cover_html(img_w, img_h))

    def check_volume(self, is_gui=False, signal=None, editline=None):
        chap_names = self.volume['chap_names']
        chap_num = len(self.volume['chap_names'])
        for chap_no, url in enumerate(self.volume['chap_urls']):
            if self.check_url(url):
                if not self.prev_fix_url(chap_no, chap_num): #先尝试反向递归修复
                    if chap_no == 0:    #第一个章节都反向修复失败 说明后面章节全部缺失，只能手动输入第一个章节，保证第一个章节一定有效
                        self.volume['chap_urls'][0] = self.hand_in_url(chap_names[chap_no], is_gui, signal, editline)
                    else:   #其余章节反向修复失败 默认使用正向修复 
                        self.missing_last_chap_list.append(chap_names[chap_no-1])
        
         #没有检测到插图页，手动输入插图页标题
        if self.color_chap_name not in self.volume['chap_names']:
            self.color_chap_name = self.hand_in_color_page_name(is_gui, signal, editline)
        self.volume['color_chap_name'] = self.color_chap_name

        #没有彩页 但主页封面存在，将主页封面设为书籍封面 
        if self.color_chap_name=='':
            self.is_color_page = False
            if not self.check_url(self.cover_url_back):
                self.img_url_map[self.cover_url_back] = str(len(self.img_url_map)).zfill(2)
                print('**************')
                print('提示：没有彩页，但主页封面存在，将使用主页的封面图片作为本卷图书封面')
                print('**************')
    
    def check_url(self, url):#当检测有问题返回True
        return ('javascript' in url or 'cid' in url)   
    
    def get_prev_url(self, chap_no): #获取前一个章节的链接
        content_html = self.get_html(self.volume['chap_urls'][chap_no], is_gbk=False)
        next_url = self.url_head + re.search(r'<div class="mlfy_page"><a href="(.*?)">上一页</a>', content_html).group(1)
        return next_url
    
    def prev_fix_url(self, chap_no, chap_num):  #反向递归修复缺失链接（后修复前），若成功修复返回True，否则返回False 
        if chap_no==chap_num-1: #最后一个章节直接选择不修复 返回False
            return False
        elif self.check_url(self.volume['chap_urls'][chap_no+1]):
            if self.prev_fix_url(chap_no+1, chap_num):
                self.volume['chap_urls'][chap_no] = self.get_prev_url(chap_no+1)
                return True
            else:
                return False
        else:
            self.volume['chap_urls'][chap_no] = self.get_prev_url(chap_no+1)
            return True
        
    def hand_in_msg(self, error_msg='', is_gui=False, signal=None, editline=None):
        # if is_gui:
        #     print(error_msg)
        #     signal.emit('hang')
        #     time.sleep(1)
        #     while not editline.isHidden():
        #         time.sleep(1)
        #     content = editline.text()
        #     editline.clear()
        # else:
        #     content = input(error_msg)

        # 该功能是为了处理哔哩轻小说的某一卷没有最开始的插图或彩页而处理的，然而我发现如果本身就没插图还要强行选择只会出现一个无法显示图片的标志，还不如一开始就是为空！
        content = ""
        return content
            
    def hand_in_url(self, chap_name, is_gui=False, signal=None, editline=None):
        error_msg = f'章节\"{chap_name}\"连接失效，请手动输入该章节链接(手机版“{self.url_head}”开头的链接):'
        return self.hand_in_msg(error_msg, is_gui, signal, editline)
    
    def hand_in_color_page_name(self, is_gui=False, signal=None, editline=None):
        if is_gui:
            error_msg = f'插图页面不存在，需要下拉选择插图页标题，若不需要插图页则保持本栏为空直接点确定：'
            editline.addItems(self.volume['chap_names'])
            editline.setCurrentIndex(-1)
        else:
            error_msg = f'插图页面不存在，需要手动输入插图页标题，若不需要插图页则不输入直接回车：'
        return self.hand_in_msg(error_msg, is_gui, signal, editline) 
    
    def get_toc(self):
        if self.is_color_page:
            ind = self.volume["chap_names"].index(self.color_chap_name)
            self.volume["chap_names"].pop(ind)
        toc_htmls = get_toc_html(self.book_name, self.volume["chap_names"])
        with open(os.path.join(self.temp_path, 'OEBPS/toc.ncx'), 'w+', encoding='utf-8') as f:
            f.write(toc_htmls)

    def get_content(self):
        content_html = get_content_html(self.book_name, self.volume['volume_name'], self.volume_no, self.author, self.publisher, self.brief, self.tag_list, len(self.volume["chap_names"]), len(os.listdir(self.img_path)), self.is_color_page)
        with open(os.path.join(self.temp_path, 'OEBPS/content.opf'), 'w+', encoding='utf-8') as f:
            f.write(content_html)

    def get_epub_head(self):
        metainf_folder = os.path.join(self.temp_path, 'META-INF')
        os.makedirs(metainf_folder, exist_ok=True)
        with open(os.path.join(metainf_folder, 'container.xml'), 'w+', encoding='utf-8') as f:
            f.write(get_container_html())
        with open(os.path.join(self.temp_path, 'mimetype'), 'w+', encoding='utf-8') as f:
            f.write('application/epub+zip')

    def get_epub(self):

        # 检查卷名是否已包含书名，如果包含则只用卷名
        # epub_file = self.epub_path + '/' + check_chars(self.book_name + '-' + self.volume['volume_name']) + '.epub'
        if self.book_name in self.volume['volume_name']:
            filename = self.volume['volume_name']
        else:
            filename = self.book_name + '-' + self.volume['volume_name']
        epub_file = self.epub_path + '/' + check_chars(filename) + '.epub'

        with zipfile.ZipFile(epub_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _, filenames in os.walk(self.temp_path):
                fpath = dirpath.replace(self.temp_path,'') #这一句很重要，不replace的话，就从根目录开始复制
                fpath = fpath and fpath + os.sep or ''
                for filename in filenames:
                    zf.write(os.path.join(dirpath, filename), fpath+filename)
        self.temp_path_io.cleanup()
        return epub_file
    
    # def buffer(self):
    #     filename = 'buffer.pkl'
    #     filepath = os.path.join(self.temp_path, filename)
    #     if os.path.isfile(filepath):
    #         with open(filepath, 'rb') as f:
    #             self.volume, self.img_url_map = pickle.load(f)
    #             self.text_path = os.path.join(self.temp_path, 'OEBPS/Text')
    #             os.makedirs(self.text_path, exist_ok=True)
    #             self.img_path = os.path.join(self.temp_path,  'OEBPS/Images')
    #             os.makedirs(self.img_path, exist_ok=True)
    #             self.color_chap_name = self.volume['color_chap_name']
    #     else:
    #         with open(filepath, 'wb') as f:
    #             pickle.dump((self.volume ,self.img_url_map), f)
    
    # def is_buffer(self):
    #     filename = 'buffer.pkl'
    #     filepath = os.path.join(self.temp_path, filename)
    #     return os.path.isfile(filepath)
