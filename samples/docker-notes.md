# Docker ve DocuMind

DocuMind altı servis kullanır: React arayüzü, FastAPI backend, Qdrant vektör veritabanı, Ollama model sunucusu, Redis kuyruğu ve Celery belge işleme worker'ı.

Docker Compose servisleri ortak bir ağ üzerinde orkestre eder. Servisler birbirlerine DNS servis adlarıyla erişir. Dışarıya yalnızca arayüzün 3000 portu açılır.

Qdrant vektörleri qdrant_data volume içinde saklar. Ollama modelleri ollama_data volume içinde kalıcıdır. Belgeler, katalog ve sohbet geçmişi documents_data volume içinde tutulur. Redis kuyruk verisi redis_data volume içinde saklanır.

NVIDIA GPU kullanımı compose.gpu.yaml ile etkinleştirilir. Varsayılan kurulum CPU üzerinde çalışır.

RAG akışı: API dosyayı kaydedip işi Redis kuyruğuna gönderir. Celery worker belgeden metin çıkarır, örtüşen parçalara ayırır, embedding üretir ve Qdrant'a yazar. Soru geldiğinde hazır belgelerin ilgili parçaları bulunur ve yerel modele kaynak olarak sunulur.
