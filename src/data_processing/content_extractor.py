#.src/data_processing/content_extractor.py
import io
import time
import random
import zipfile
from PyPDF2 import PdfReader 
import pdfplumber
import requests
import urllib.robotparser
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from config import settings # Assumindo que 'settings' existe e contém logger e USER_AGENTS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from newspaper import Article

class ContentExtractor:
    """
    Orquestra a extração de conteúdo, usando o método certo para cada domínio e formato.
    """

    def __init__(self):
        self.driver_path = ChromeDriverManager().install()
        self.newspaper_config = {
            'browser_user_agent': random.choice(settings.USER_AGENTS),
            'request_timeout': 10,
            'follow_meta_refresh': True
        }
        self.request_headers = {'User-Agent': random.choice(settings.USER_AGENTS)}

    def _setup_chrome_options(self, user_agent: str = None):
        """
        Configura e retorna um NOVO objeto Options do Chrome.
        Permite adicionar um user_agent específico.
        """
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        if user_agent:
            options.add_argument(f"user-agent={user_agent}")
        return options

    def _is_allowed_by_robots(self, url: str) -> bool:
        try:
            parsed_url = urlparse(url)
            robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            return rp.can_fetch(self.request_headers['User-Agent'], url)
        except Exception:
            return True # Em caso de falha na leitura, permite por padrão

    def _extract_from_pdf(self, file_content: bytes) -> str | None:
        """
        Extrai texto de um conteúdo PDF usando PyPDF2 e pdfplumber, priorizando PyPDF2
        pela velocidade e usando pdfplumber como fallback para melhor formatação.
        """
        text_pypdf = ""
        text_pdfplumber = ""

        try:
            # Tenta extrair com PyPDF2 primeiro
            with io.BytesIO(file_content) as data:
                reader = PdfReader(data)
                for page in reader.pages:
                    try:
                        extracted_text = page.extract_text()
                        if extracted_text:
                            text_pypdf += extracted_text + "\n\n"
                    except Exception as e:
                        settings.logger.debug(f"Erro ao extrair página com PyPDF2: {e}")
            
            if text_pypdf.strip(): # Se PyPDF2 conseguiu extrair algo, use-o
                settings.logger.info("Extração de PDF bem-sucedida com PyPDF2.")
                return text_pypdf.strip()

        except Exception as e:
            settings.logger.error(f"Erro geral PyPDF2, tentando pdfplumber: {str(e)[:200]}")
            # Continua para pdfplumber se PyPDF2 falhar completamente

        # Fallback para pdfplumber
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages:
                    try:
                        # Limita o tamanho da página para evitar memory explosion
                        if len(text_pdfplumber) < 1000000:  # ~1MB
                            page_text = page.extract_text(x_tolerance=2)
                            if page_text:
                                text_pdfplumber += page_text + "\n\n"
                    finally:
                        page.flush_cache()  # Libera recursos imediatamente
            
            if text_pdfplumber.strip():
                settings.logger.info("Extração de PDF bem-sucedida com pdfplumber.")
                return text_pdfplumber.strip()
            else:
                settings.logger.warning("Nenhum texto extraído do PDF com PyPDF2 ou pdfplumber.")
                return None

        except Exception as e:
            settings.logger.error(f"Erro pdfplumber: {str(e)[:200]}")
            return None

    def _extract_from_cvm_zip(self, file_content: bytes) -> str | None:
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as z:
                text_file_name = next((name for name in z.namelist() if name.lower().endswith(('.txt', '.csv'))), None)
                if text_file_name:
                    with z.open(text_file_name) as text_file:
                        return text_file.read().decode('latin-1', errors='ignore')
            return None
        except Exception as e:
            settings.logger.error(f"Erro ao processar ZIP da CVM: {e}")
            return None
    
    def _handle_cvm_document_page(self, url: str, depth=0) -> str | None:
        if depth > 5:  # Previne recursão infinita
            settings.logger.warning(f"CVM: Profundidade máxima de recursão atingida para {url}")
            return None
            
        try:
            response = requests.get(url, headers={
                'User-Agent': random.choice(settings.USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9',
                'Connection': 'keep-alive'
            }, timeout=30, allow_redirects=True)
            
            content_type = response.headers.get('Content-Type', '').lower()
            
            # --- Adição de Logs para Diagnóstico ---
            settings.logger.info(f"CVM [{depth}]: URL: {url} | Final URL (após redirect): {response.url} | Content-Type: {content_type} | Status Code: {response.status_code} | Size: {len(response.content)} bytes")
            # --- Fim dos Logs de Diagnóstico ---

            # Tentativa de detectar PDF pelo início do conteúdo, caso Content-Type esteja errado
            if response.content.startswith(b'%PDF-'):
                settings.logger.info(f"CVM: Conteúdo identificado como PDF via magic number para {url}. Content-Type original: {content_type}")
                return self._extract_from_pdf(response.content)
            
            # Trata PDF diretamente (pelo Content-Type)
            if 'application/pdf' in content_type:
                settings.logger.info(f"CVM: Content-Type indica PDF para {url}.")
                return self._extract_from_pdf(response.content)
                
            # Trata ZIP
            if 'application/zip' in content_type:
                settings.logger.info(f"CVM: Content-Type indica ZIP para {url}.")
                return self._extract_from_cvm_zip(response.content)
                
            # Analisa HTML para encontrar iframe ou texto
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Tenta encontrar o iframe principal
            iframe = soup.find('iframe', id='iFrameFormulariosFilho')
            
            # Fallback: Procura por qualquer iframe com src
            if not iframe:
                iframe = soup.find('iframe', src=True)
            
            if iframe and iframe['src']:
                new_url = iframe['src']
                # Resolve URLs relativas
                if not new_url.startswith('http'):
                    parsed = urlparse(url)
                    new_url = f"{parsed.scheme}://{parsed.netloc}{new_url}"
                settings.logger.info(f"CVM: Encontrado iframe. Seguindo para {new_url} (depth {depth + 1}).")
                return self._handle_cvm_document_page(new_url, depth + 1)
            
            # Fallback: Extrai todo o texto da página HTML
            settings.logger.info(f"CVM: Extraindo texto HTML genérico para {url}.")
            return soup.get_text('\n', strip=True)
            
        except requests.exceptions.RequestException as req_e:
            settings.logger.error(f"CVM Request Error for {url}: {req_e}")
            return None
        except Exception as e:
            settings.logger.error(f"CVM General Error for {url}: {str(e)}")
            return None
        
    def _extract_with_html_strategies(self, url: str) -> str | None:
        # Tentativa com Newspaper3k
        try:
            article = Article(url, config=self.newspaper_config)
            article.download()
            article.parse()
            if article.text and len(article.text) > 250:
                settings.logger.info(f"Extração HTML bem-sucedida com Newspaper3k para {url}. Tamanho: {len(article.text)} chars. Conteúdo (primeiros 200 chars): {article.text[:200]}...")
                return article.text
            else:
                settings.logger.debug(f"Newspaper3k falhou ou extraiu pouco texto (<250 chars) para {url}. Tamanho: {len(article.text) if article.text else 0} chars.")
        except Exception as e:
            settings.logger.debug(f"Newspaper3k falhou completamente para {url}: {e}")
            pass

        # Fallback com Selenium
        driver = None
        try:
            user_agent = random.choice(settings.USER_AGENTS)
            options = self._setup_chrome_options(user_agent=user_agent)
            
            service = Service(executable_path=self.driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(30)
            driver.get(url)
            
            # ADICIONADO: Um pequeno delay para dar tempo à página de carregar JavaScript.
            # No notebook, você usa 3 segundos. Vamos tentar um valor conservador aqui.
            time.sleep(random.uniform(2, 4)) 
            
            # Espera mais inteligente por elementos do corpo do texto, seletor mais específico
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "body article, body .main-content, body .post, body p"))
                # Adicionado 'body p' como fallback para garantir que pelo menos algum texto de parágrafo esteja presente
            )
            
            # Tentativa com Newspaper no HTML renderizado
            try:
                article = Article("", config=self.newspaper_config)
                article.set_html(driver.page_source)
                article.parse()
                if article.text and len(article.text) > 250:
                    settings.logger.info(f"Extração HTML bem-sucedida com Newspaper3k (Selenium renderizado) para {url}. Tamanho: {len(article.text)} chars. Conteúdo (primeiros 200 chars): {article.text[:200]}...")
                    return article.text
                else:
                    settings.logger.debug(f"Newspaper3k (Selenium renderizado) falhou ou extraiu pouco texto (<250 chars) para {url}. Tamanho: {len(article.text) if article.text else 0} chars.")
            except Exception as e:
                settings.logger.debug(f"Newspaper3k (Selenium renderizado) falhou completamente para {url}: {e}")
                pass
            
            # Fallback genérico com BeautifulSoup
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Tenta seletores mais específicos para o conteúdo principal
            main_content = soup.select_one('article, .main-content, .post, .content-body, .article-body, #content-main')
            
            extracted_text = ""
            if main_content:
                extracted_text = main_content.get_text("\n", strip=True)
                settings.logger.info(f"Extração HTML bem-sucedida com BeautifulSoup (seletor) para {url}. Tamanho: {len(extracted_text)} chars. Conteúdo (primeiros 200 chars): {extracted_text[:200]}...")
            else:
                # Se nenhum seletor específico funcionar, tenta o corpo inteiro
                extracted_text = soup.body.get_text("\n", strip=True)
                settings.logger.info(f"Extração HTML bem-sucedida com BeautifulSoup (body fallback) para {url}. Tamanho: {len(extracted_text)} chars. Conteúdo (primeiros 200 chars): {extracted_text[:200]}...")
            
            if len(extracted_text) > 250: # Verificação para garantir texto significativo
                return extracted_text
            else:
                settings.logger.warning(f"Extração HTML com BeautifulSoup (ambos seletores) resultou em pouco texto (<250 chars) para {url}. Tamanho: {len(extracted_text)} chars.")
                return None # Retorna None se o texto for insignificante
        except TimeoutException:
            settings.logger.error(f"Timeout de carregamento de página excedido para '{url}' após 30 segundos.")
            # Retorna None, pois a extração falhou devido ao timeout
            return None
        except Exception as e:
            settings.logger.error(f"Erro Selenium para {url}: {e}")
            return None
        finally:
            if driver:
                driver.quit()

    def extract_text_from_url(self, url: str) -> str | None:
        """ MÉTODO PÚBLICO (O "Despachante Inteligente"): orquestra a extração. """
        settings.logger.info(f"Iniciando extração para URL: {url}")
        if not self._is_allowed_by_robots(url):
            settings.logger.warning(f"Extração bloqueada por robots.txt para {url}.")
            return "EXTRACAO_BLOQUEADA_POR_ROBOTS_TXT"
        
        hostname = urlparse(url).hostname or ""
        
        if "rad.cvm.gov.br" in hostname:
            settings.logger.info(f"URL reconhecida como CVM: {url}. Usando _handle_cvm_document_page.")
            return self._handle_cvm_document_page(url)
        else:
            settings.logger.info(f"URL não CVM: {url}. Usando _extract_with_html_strategies.")
            # O texto extraído é retornado aqui. O que a sua aplicação faz com ele?
            extracted_content = self._extract_with_html_strategies(url)
            
            # Adicionado log para ver o que é retornado antes de sair do método público
            if extracted_content:
                settings.logger.info(f"Conteúdo extraído com sucesso para {url}. Tamanho final: {len(extracted_content)} chars.")
            else:
                settings.logger.warning(f"Nenhum conteúdo válido extraído para {url}.")
            
            return extracted_content