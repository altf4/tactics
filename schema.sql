-- To reload the tables:
--   mysql --user=[USER] --password=[PASS] --database=tactics < schema.sql

SET SESSION time_zone = "+0:00";
ALTER DATABASE CHARACTER SET "utf8";

DROP TABLE IF EXISTS users;
CREATE TABLE users (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(20) NOT NULL UNIQUE,
    hash VARCHAR(100) NOT NULL,
    elo INT NOT NULL,
    KEY (id)
);
