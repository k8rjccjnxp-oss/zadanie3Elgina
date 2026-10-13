-- Демонстрационные данные. Пароли для пользователей создаются приложением через Werkzeug.
INSERT INTO categories(name) VALUES ('Велосипеды'), ('Аксессуары'), ('Запчасти');
INSERT INTO suppliers(name) VALUES ('ВелоТрейд'), ('СпортСнаб'), ('Мир деталей');
INSERT INTO products(name,category_id,description,manufacturer,supplier_id,price,unit,stock,discount) VALUES
('Городской велосипед',1,'Удобный велосипед для города','Velomax',1,25990,'шт.',12,10),
('Горный велосипед',1,'Для прогулок по пересечённой местности','TrailPro',2,38900,'шт.',5,0),
('Шлем защитный',2,'Регулируемый защитный шлем','SafeRide',2,3200,'шт.',0,15),
('Набор тормозных колодок',3,'Комплект для обслуживания тормозов','BikeParts',3,850,'компл.',24,5),
('Велосипедный фонарь',2,'Передний LED-фонарь','BrightWay',1,1450,'шт.',8,0);
INSERT INTO orders(article,status,pickup_address,order_date) VALUES
('ORD-1001','Новый','Пункт выдачи № 1','2026-10-01 12:30:00'),
('ORD-1002','В обработке','Пункт выдачи № 2','2026-10-03 15:10:00');
INSERT INTO order_items(order_id,product_id,quantity) VALUES (1,1,1),(1,4,2),(2,2,1);
