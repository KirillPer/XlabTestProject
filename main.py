from tinkoff_voicekit_client import ClientSTT
import uuid
import re
import logging
import os
import datetime
import psycopg2
import sys


# функция перевода аудио в текст с помощью API
# на входе путь к файлу, ключи апи соответственно
def speech_to_text(file_path: str, api_key: str, secret_key: str):
    client = ClientSTT(api_key, secret_key)

    audio_config = {
        "encoding": "LINEAR16",
        "sample_rate_hertz": 8000,
        "num_channels": 1
    }
    return client.recognize(file_path, audio_config)


# функция логирования ошибок
# на входе текст ошибки
def err_log_build(error_text):
    logger = logging.getLogger('err_log')
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler('errors.log')
    fh.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.info('error text: %s\n', error_text)
    logger.removeHandler(fh)
    logging.shutdown()
    del logger, fh


# функция логирования результатов распознаваний
# уникальный ИД, результат классификации(1\0), номер телефона, длительность аудио, текст после распознавания
def rec_log_build(action_id, class_res, telephone_number, audio_duration, res_text):
    logger = logging.getLogger('rec_log')
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler('recognition.log')
    fh.setLevel(logging.INFO)
    logger.addHandler(fh)

    logger.info('---------------BEGIN---------------')
    logger.info('ID: %s', action_id)
    logger.info('DATE: %s', datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S"))
    logger.info('CLASSIFICATION RESULT: %s', class_res)
    logger.info('TELEPHONE NUMBER: %s', telephone_number)
    logger.info('AUDIO DURATION: %s', audio_duration)
    logger.info('RECOGNITION TEXT: %s', res_text)
    logger.info('----------------END---------------\n\n\n')
    logger.removeHandler(fh)
    logging.shutdown()
    del logger, fh


# функция перевода классификации в текст
# на входе результат запроса, этап распознавания
def class_rec_text(response, recognition_stage):
    for variant in response:
        for alternative in variant['alternatives']:
            rec_flag = classification_recognition(alternative['transcript'], recognition_stage)
            if rec_flag != -1:
                res_text = rec_flag[1]
                if recognition_stage == 1:
                    if rec_flag[0] == 0:
                        return 'автоответчик', res_text
                    elif rec_flag[0] == 1:
                        return 'человек', res_text
                if recognition_stage == 2:
                    if rec_flag[0] == 0:
                        return 'отрицательно', res_text
                    elif rec_flag[0] == 1:
                        return 'положительно', res_text


# функция классификации распознавания
# на входе распознанных текст, этап распознавания
def classification_recognition(response_text, recognition_stage):
    # если текст имеется
    if len(response_text) > 0:
        # и пользователь указал шаг 1
        if recognition_stage == 1:
            # ищем слова в тексте 'автоответчик' и 'сигнал'
            # это самые частоиспользуемые слова в сообщениях автоответчика
            # если нашли - автоответчик, нет - человек
            if response_text.find('автоответчик') and response_text.find('сигнал') != -1:
                return 0, response_text
            else:
                return 1, response_text
        # если пользователь указал шаг 2
        elif recognition_stage == 2:
            # ищем в строке отрицания
            denial = re.findall(r'(\bне)', response_text)
            # если отрицания имеются - ответ отрицательный
            if len(denial) > 0:
                return 0, response_text
            # иначе положительный
            else:
                return 1, response_text
    # возвращаем -1 в случае отсутствия текста
    else:
        return -1


# основная функция
# на входе путь до аудиофайла, номер телефона, флаг сохранения в бд(0 или 1), этап распознавания(1 или 2)
def recognition_logging(file_path: str, telephone_number: str,
                        db_save_flag: int, recognition_stage: int):
    # если файл существует
    if os.path.isfile(file_path):

        # пробуем совершить запрос для распознавания
        try:
            response = speech_to_text(file_path, "API_KEY", "secret_key")
        # обрабатываем и логируем ошибку в случае неудачи
        except Exception as error:
            err_log_build(str(error))
            raise error

        # определяем АО\человек, или отрицательно\положительно
        class_res = class_rec_text(response, recognition_stage)[0]
        # получаем текст распознавания
        res_text = class_rec_text(response, recognition_stage)[1]
        # извлекаем длительность аудио
        audio_duration = response[-1]['end_time']
        # формируем уникальный ИД
        action_id = uuid.uuid4().int & (1 << 50)-1
        # логируем
        rec_log_build(action_id, class_res, telephone_number, audio_duration, res_text)

        # если нужно сохранять в базу - сохраняем
        if db_save_flag == 1:
            db_save(action_id, class_res, telephone_number, audio_duration, res_text)

        # удаляем аудио
        os.remove(file_path)
    else:  # иначе ошибка - отсутствие файла
        err_log_build("File: " + file_path + " not found")
        raise Exception("File %s not found" % file_path)


# функция сохранения записи в БД
# на входе те же параметры, что при логировании
def db_save(action_id, class_res, telephone_number, audio_duration, res_text):

    # пробуем соединиться с бд
    try:
        conn = psycopg2.connect(database="postgres",
                                user="postgres",
                                password="postgres",
                                host="localhost",
                                port="5432")
    # ошибка и логирование в случае неудачи
    except psycopg2.OperationalError as error:
        err_log_build(error)
        raise error
    # создаем курсор и формируем запрос
    cursor = conn.cursor()
    query = "INSERT INTO Log VALUES (%s, %s, %s, %s, %s, %s, %s, %s);"
    # выполняем запрос
    try:
        data = (action_id, datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S"), class_res,
                telephone_number, audio_duration, res_text, 2, 1)

        cursor.execute(query, data)
        conn.commit()
    # ошибка и логирование в случае неудачи
    except Exception as error:
        err_log_build(error)
        raise error
    # закрываем соединение в любом случае
    finally:
        conn.close()


# примеры команд для выполнения
# ------------------------------------------------------------
# python main.py C:\Users\You\Downloads\2.wav 6755443466 1 1
# python main.py C:\Users\You\Downloads\1.wav 9732486465 1 1
# python main.py C:\Users\asmod\Downloads\3.wav 9732486465 1 2
# python main.py C:\Users\You\Downloads\4.wav 9732286465 1 2
# ------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise Exception("There must be 4 parameters")
    else:
        recognition_logging(file_path=sys.argv[1], telephone_number=str(sys.argv[2]),
                            db_save_flag=int(sys.argv[3]), recognition_stage=int(sys.argv[4]))






