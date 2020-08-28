import psycopg2


def sql_script(first_date: str, second_date: str = None):

    conn = psycopg2.connect(database="postgres",
                            user="postgres",
                            password="postgres",
                            host="localhost",
                            port="5432")
    cursor = conn.cursor()

    if second_date:
        query = "SELECT to_date(l.datetime, 'DD-MM-YYYY'), count(l.datetime), l.class_res, p.name, s.name FROM log l " \
                "JOIN server s ON l.server_id = s.id "\
                "JOIN project p ON l.project_id = p.id " \
                "WHERE to_date(l.datetime, 'DD-MM-YYYY') >= %s " \
                "AND to_date(l.datetime, 'DD-MM-YYYY') <= %s " \
                "GROUP BY to_date(l.datetime, 'DD-MM-YYYY'), l.class_res, p.name, s.name"

        cursor.execute(query, (first_date, second_date))
    else:
        query = "SELECT l.datetime, l.class_res FROM log l " \
                "WHERE to_date(l.datetime, 'DD-MM-YYYY') = %s;"

        cursor.execute(query, (first_date, ))

    for row in cursor:
        print(row)
    conn.commit()
    conn.close()


sql_script('27-08-2020', '28-08-2020')


