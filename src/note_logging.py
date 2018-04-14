import logging

LOGGING_FORMAT = '%(asctime)s [%(filename)s:%(lineno)s - %(funcName)20s() ]' +\
                 '%(message)s'
LOGGING_LEVEL = logging.INFO
#LOGGING_LEVEL = logging.DEBUG
#LOGGING_DATE_FORMAT = '%Y-%m-%d %h:%M'
# '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=LOGGING_LEVEL)



def debug(msg):
    logging.debug(msg)





