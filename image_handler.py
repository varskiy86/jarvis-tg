"""
Обработка изображений для J.A.R.V.I.S.
- Генерация через Pollinations AI (бесплатно, без API ключа)
- Анализ/редактирование через Gemini
- Поиск похожих изображений
"""
import aiohttp
import io
import base64
from typing import Optional, List, Tuple
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import google.generativeai as genai
from config import config


class ImageHandler:
    """Обработчик изображений"""
    
    # Бесплатные API для генерации
    POLLINATIONS_URL = "https://image.pollinations.ai/prompt/"
    
    def __init__(self):
        self.gemini_model = genai.GenerativeModel(config.GEMINI_MODEL)
    
    async def generate_image(self, prompt: str, width: int = 1024, height: int = 1024, 
                            seed: Optional[int] = None, enhance: bool = True) -> Optional[bytes]:
        """
        Генерация изображения через Pollinations AI (бесплатно)
        
        Args:
            prompt: Описание что сгенерировать
            width: Ширина (по умолчанию 1024)
            height: Высота (по умолчанию 1024)
            seed: Сид для воспроизводимости
            enhance: Улучшить промпт автоматически
        
        Returns:
            bytes: Изображение в формате PNG
        """
        try:
            # Улучшаем промпт для лучшего результата
            if enhance:
                enhanced_prompt = self._enhance_prompt(prompt)
            else:
                enhanced_prompt = prompt
            
            # Формируем URL
            params = f"?width={width}&height={height}&nologo=true"
            if seed:
                params += f"&seed={seed}"
            
            # Кодируем промпт для URL
            import urllib.parse
            encoded_prompt = urllib.parse.quote(enhanced_prompt)
            url = f"{self.POLLINATIONS_URL}{encoded_prompt}{params}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        return image_data
                    else:
                        print(f"Ошибка генерации: {response.status}")
                        return None
                        
        except Exception as e:
            print(f"Ошибка при генерации изображения: {e}")
            return None
    
    def _enhance_prompt(self, prompt: str) -> str:
        """Улучшает промпт для лучшей генерации"""
        enhancements = [
            "high quality", "detailed", "professional", "8k"
        ]
        
        # Проверяем, есть ли уже улучшающие слова
        prompt_lower = prompt.lower()
        to_add = [e for e in enhancements if e not in prompt_lower]
        
        if to_add:
            return f"{prompt}, {', '.join(to_add[:2])}"
        return prompt
    
    async def analyze_image(self, image_bytes: bytes, user_request: str = "Опиши это изображение") -> str:
        """
        Анализ изображения через Gemini
        
        Args:
            image_bytes: Байты изображения
            user_request: Что сделать с изображением (описать, изменить и т.д.)
        
        Returns:
            str: Ответ от AI
        """
        try:
            # Загружаем изображение
            image = Image.open(io.BytesIO(image_bytes))
            
            # Конвертируем в формат для Gemini
            img_byte_arr = io.BytesIO()
            image.convert('RGB').save(img_byte_arr, format='JPEG', quality=85)
            img_byte_arr.seek(0)
            
            # Отправляем в Gemini
            response = await self._analyze_with_gemini(img_byte_arr.getvalue(), user_request)
            return response
            
        except Exception as e:
            return f"Ошибка анализа изображения: {str(e)}"
    
    async def _analyze_with_gemini(self, image_bytes: bytes, prompt: str) -> str:
        """Внутренний метод анализа через Gemini"""
        try:
            # Создаём parts для запроса
            import asyncio
            
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }
            
            # Формируем промпт
            full_prompt = f"""{config.SYSTEM_PROMPT}

Запрос пользователя к изображению: {prompt}

Ответь в своём фирменном стиле J.A.R.V.I.S."""
            
            # Отправляем запрос
            response = await asyncio.to_thread(
                self.gemini_model.generate_content,
                [full_prompt, image_part]
            )
            
            return response.text
            
        except Exception as e:
            return f"Ошибка Gemini при анализе: {str(e)}"
    
    async def edit_image(self, image_bytes: bytes, edit_type: str, 
                        intensity: float = 1.0) -> Optional[bytes]:
        """
        Базовое редактирование изображения (локально, без AI)
        
        Args:
            image_bytes: Байты изображения
            edit_type: Тип редактирования (blur, sharpen, contrast, brightness, bw, sepia)
            intensity: Интенсивность эффекта (0.1 - 2.0)
        
        Returns:
            bytes: Отредактированное изображение
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            
            if edit_type == "blur":
                image = image.filter(ImageFilter.GaussianBlur(radius=intensity * 5))
            
            elif edit_type == "sharpen":
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(intensity * 2)
            
            elif edit_type == "contrast":
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(intensity * 1.5)
            
            elif edit_type == "brightness":
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(intensity)
            
            elif edit_type == "bw" or edit_type == "blackwhite":
                image = ImageOps.grayscale(image)
            
            elif edit_type == "sepia":
                image = self._apply_sepia(image)
            
            # Сохраняем результат
            output = io.BytesIO()
            image.save(output, format='PNG')
            output.seek(0)
            return output.getvalue()
            
        except Exception as e:
            print(f"Ошибка редактирования: {e}")
            return None
    
    def _apply_sepia(self, image: Image.Image) -> Image.Image:
        """Применяет сепию к изображению"""
        # Конвертируем в RGB если нужно
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Матрица сепии
        sepia_matrix = [
            0.393, 0.769, 0.189, 0,
            0.349, 0.686, 0.168, 0,
            0.272, 0.534, 0.131, 0
        ]
        
        return image.convert('RGB', sepia_matrix)
    
    async def generate_variations(self, image_bytes: bytes, num_variations: int = 4) -> List[bytes]:
        """
        Генерация вариаций изображения (описывает → генерирует новые)
        
        Args:
            image_bytes: Исходное изображение
            num_variations: Количество вариаций
        
        Returns:
            List[bytes]: Список изображений
        """
        try:
            # Сначала анализируем изображение
            description = await self.analyze_image(image_bytes, 
                "Опиши подробно что на этом изображении. Перечисли основные элементы, стиль, цвета, настроение.")
            
            variations = []
            for i in range(num_variations):
                # Добавляем случайность к промпту
                variation_prompt = f"{description}, variation {i+1}, different angle, same style"
                
                img = await self.generate_image(variation_prompt, seed=i*1000)
                if img:
                    variations.append(img)
            
            return variations
            
        except Exception as e:
            print(f"Ошибка генерации вариаций: {e}")
            return []


# Глобальный экземпляр
image_handler = ImageHandler()
