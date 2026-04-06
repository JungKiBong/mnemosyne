job "ray-cluster" {
  datacenters = ["dc1"]
  type = "service"

  # ==========================================
  # Ray Head Node 
  # ==========================================
  group "ray-head" {
    count = 1

    # 포트포워딩과 고정 IP 접근을 위해 101 서버로 헤드를 고정
    constraint {
      attribute = "${attr.unique.hostname}"
      value     = "CT101"
    }

    task "head" {
      driver = "docker"

      config {
        image = "rayproject/ray:latest-py310"
        network_mode = "host" # 호스트 네트워크 사용 (통신 및 포트 개방 직통)
        
        # Ray가 Nomad 할당량 안에서 놀 수 있도록 제한
        command = "ray"
        args = [
          "start",
          "--head",
          "--port=6379",
          "--dashboard-host=0.0.0.0",
          "--metrics-export-port=8080",
          "--num-cpus=2",
          "--block"
        ]
      }

      # Nomad 스케줄러에게 요구하는 자원 할당량
      resources {
        cpu    = 2000 # 약 2 Core
        memory = 2048 # 2 GB RAM (가상 컨테이너 환경)
      }
    }
  }

  # ==========================================
  # Ray Worker Nodes
  # ==========================================
  group "ray-worker" {
    # 105, 106, 107, 108번 워커 노드용 4개 배포
    count = 4

    # 헤드가 뜬 101번을 제외한 나머지 노드들에 균등하게 분배
    constraint {
      attribute = "${attr.unique.hostname}"
      operator  = "!="
      value     = "CT101"
    }

    # 각자 다른 노드에 배포 (Anti-affinity)
    constraint {
      operator  = "distinct_hosts"
      value     = "true"
    }

    task "worker" {
      driver = "docker"

      config {
        image = "rayproject/ray:latest-py310"
        network_mode = "host"
        
        command = "ray"
        args = [
          "start",
          "--address=192.168.35.101:6379",
          "--num-cpus=4", # 워커 노드는 좀 더 태스크 처리에 집중
          "--block"
        ]
      }

      resources {
        cpu    = 4000 # 약 4 Core
        memory = 4096 # 4 GB RAM
      }
    }
  }
}
